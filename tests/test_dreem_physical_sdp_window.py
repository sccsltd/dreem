import json
import types
import tempfile
import unittest
from pathlib import Path

from tools import dreem_physical_sdp_window as window


class FingerbotPressTests(unittest.TestCase):
    def test_fingerbot_press_does_not_leak_token_in_summary_or_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token_path = root / "login.raw.json"
            token_path.write_text(json.dumps({"result": {"token": "secret-token"}}))

            requested_urls = []

            class Response:
                status = 200

                def read(self):
                    return b'{"ok":true,"message":"pressed"}'

            def opener(request, timeout, context):
                requested_urls.append(request.full_url)
                return Response()

            result = window.fingerbot_press(
                base_url="https://fingerbot.local",
                token_json=token_path,
                press_ms=8000,
                angle_enum="2",
                out_dir=root,
                opener=opener,
            )

            self.assertTrue(result["token_loaded"])
            self.assertEqual(result["http_status"], 200)
            self.assertIn("press_time=8000", requested_urls[0])
            self.assertIn("angle_enum=2", requested_urls[0])
            self.assertIn("auth_token=secret-token", requested_urls[0])
            self.assertNotIn("secret-token", json.dumps(result))
            self.assertNotIn("secret-token", Path(result["response_redacted"]).read_text())


class UbootFallbackTests(unittest.TestCase):
    def test_boot_uboot_scripts_stops_after_ums_disk_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = [root / "first.uuu", root / "second.uuu", root / "third.uuu"]
            for script in scripts:
                script.write_text("uuu_version 1.4.72\n")

            commands = []
            summaries = iter(
                [
                    {"disk_detected": False},
                    {"disk_detected": True, "disk": "/dev/sdz"},
                ]
            )

            def runner(cmd, *, cwd, out, timeout):
                commands.append((cmd, cwd, out, timeout))
                return {"cmd": cmd, "cwd": str(cwd), "out": str(out), "returncode": 0}

            def waiter(proc, out_dir, timeout):
                return next(summaries)

            result = window.boot_uboot_scripts(
                scripts,
                out_dir=root,
                ums_proc=object(),
                post_boot_wait=12,
                runner=runner,
                waiter=waiter,
            )

            self.assertEqual([item[0][-1] for item in commands], ["first.uuu", "second.uuu"])
            self.assertTrue(result["ums_summary"]["disk_detected"])
            self.assertEqual(len(result["attempts"]), 2)
            self.assertEqual(result["attempts"][1]["script"], str(scripts[1].resolve()))

    def test_boot_uboot_scripts_tries_all_scripts_when_no_disk_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = [root / "first.uuu", root / "second.uuu"]
            for script in scripts:
                script.write_text("uuu_version 1.4.72\n")

            commands = []

            def runner(cmd, *, cwd, out, timeout):
                commands.append(cmd)
                return {"cmd": cmd, "cwd": str(cwd), "out": str(out), "returncode": 0}

            def waiter(proc, out_dir, timeout):
                return {"disk_detected": False}

            result = window.boot_uboot_scripts(
                scripts,
                out_dir=root,
                ums_proc=object(),
                post_boot_wait=12,
                runner=runner,
                waiter=waiter,
            )

            self.assertEqual([cmd[-1] for cmd in commands], ["first.uuu", "second.uuu"])
            self.assertFalse(result["ums_summary"]["disk_detected"])
            self.assertEqual(len(result["attempts"]), 2)


class PowerCycleCueTests(unittest.TestCase):
    def test_power_cycle_with_button_hold_cues_operator_before_charger_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []
            summary = {"charger_actions": [], "fingerbot_actions": []}
            args = types.SimpleNamespace(
                charger_helper=root / "plug.sh",
                charger_on_delay=5,
                fingerbot_hold_during_charger_on_ms=8000,
                charger_on_during_hold_delay=2,
                fingerbot_base_url="https://fingerbot.local",
                fingerbot_token_json=root / "login.raw.json",
                fingerbot_angle_enum="2",
                operator_cue_countdown=0,
            )

            def sleeper(seconds):
                calls.append(("sleep", seconds))

            def charger_fn(helper, action, out_dir):
                calls.append(("charger", action))
                return {"action": action}

            def press_thread_fn(**kwargs):
                calls.append(("fingerbot_start", kwargs["press_ms"]))

                class Thread:
                    def join(self, timeout):
                        calls.append(("fingerbot_join", timeout))

                    def is_alive(self):
                        return False

                return Thread(), {"result": {"action": "fingerbot_press", "press_ms": kwargs["press_ms"]}}

            def cue_fn(summary, message, countdown_seconds, sleeper, printer):
                calls.append(("cue", message))

            window.perform_power_cycle(
                args,
                out_dir=root,
                summary=summary,
                sleeper=sleeper,
                charger_fn=charger_fn,
                press_thread_fn=press_thread_fn,
                cue_fn=cue_fn,
            )

            cue_index = next(i for i, call in enumerate(calls) if call[0] == "cue")
            charger_on_index = calls.index(("charger", "turn_on"))
            self.assertLess(cue_index, charger_on_index)
            self.assertIn(("fingerbot_start", 8000), calls)
            self.assertEqual(summary["charger_actions"], [{"action": "turn_off"}, {"action": "turn_on"}])
            self.assertEqual(summary["fingerbot_actions"][0]["press_ms"], 8000)

    def test_power_cycle_without_button_hold_cues_operator_before_charger_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []
            summary = {"charger_actions": [], "fingerbot_actions": []}
            args = types.SimpleNamespace(
                charger_helper=root / "plug.sh",
                charger_on_delay=5,
                fingerbot_hold_during_charger_on_ms=None,
                operator_cue_countdown=0,
            )

            def sleeper(seconds):
                calls.append(("sleep", seconds))

            def charger_fn(helper, action, out_dir):
                calls.append(("charger", action))
                return {"action": action}

            def cue_fn(summary, message, countdown_seconds, sleeper, printer):
                calls.append(("cue", message))

            window.perform_power_cycle(
                args,
                out_dir=root,
                summary=summary,
                sleeper=sleeper,
                charger_fn=charger_fn,
                cue_fn=cue_fn,
            )

            cue_index = next(i for i, call in enumerate(calls) if call[0] == "cue")
            charger_on_index = calls.index(("charger", "turn_on"))
            self.assertLess(cue_index, charger_on_index)
            self.assertEqual(summary["charger_actions"], [{"action": "turn_off"}, {"action": "turn_on"}])
            self.assertEqual(summary["fingerbot_actions"], [])


if __name__ == "__main__":
    unittest.main()
