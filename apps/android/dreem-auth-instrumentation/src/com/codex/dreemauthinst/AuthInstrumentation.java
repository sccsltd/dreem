package com.codex.dreemauthinst;

import android.accounts.Account;
import android.accounts.AccountManager;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Process;
import android.util.JsonWriter;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class AuthInstrumentation extends Instrumentation {
    private static final String GOOGLE_ACCOUNT_TYPE = "com.google";
    private static final String AUTH_TOKEN_TYPE = "oauth2:profile email";

    private Context targetContext;
    private File runDir;
    private final Bundle status = new Bundle();

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        super.onStart();
        try {
            targetContext = getTargetContext();
            runDir = new File(targetContext.getFilesDir(), "codex-auth-probe-" + System.currentTimeMillis());
            runDir.mkdirs();
            put("run_dir", runDir.getAbsolutePath());
            put("target_package", targetContext.getPackageName());
            put("uid", Integer.toString(Process.myUid()));
            runProbe();
        } catch (Exception e) {
            put("fatal_error", e.getClass().getSimpleName() + ":" + safeMessage(e));
            writeFinalSummary(false, "fatal_error");
        } finally {
            finish(0, status);
        }
    }

    private void runProbe() throws Exception {
        AccountManager accountManager = AccountManager.get(targetContext);
        Account[] accounts = accountManager.getAccountsByType(GOOGLE_ACCOUNT_TYPE);
        writeAccountsSummary(accounts);
        put("google_account_count", Integer.toString(accounts.length));
        if (accounts.length == 0) {
            writeFinalSummary(false, "no_google_accounts");
            return;
        }

        for (int i = 0; i < accounts.length; i++) {
            Account account = accounts[i];
            put("account_" + i + "_sha16", sha16(account.name));
            try {
                Bundle result = accountManager.getAuthToken(account, AUTH_TOKEN_TYPE, null, false, null, null)
                        .getResult(60, TimeUnit.SECONDS);
                Intent intent = result.getParcelable(AccountManager.KEY_INTENT);
                if (intent != null) {
                    put("account_" + i + "_needs_intent", "true");
                    savePrivate("auth_intent_" + i + ".txt", intent.toUri(0));
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    targetContext.startActivity(intent);
                    writeFinalSummary(false, "requires_auth_intent");
                    return;
                }
                String token = result.getString(AccountManager.KEY_AUTHTOKEN);
                if (token == null || token.length() == 0) {
                    put("account_" + i + "_token_error", "empty_token");
                    continue;
                }
                savePrivate("google_token_" + i + ".secret", token);
                put("account_" + i + "_google_token_len", Integer.toString(token.length()));
                put("account_" + i + "_google_token_sha16", sha16(token));
                ExchangeResult exchange = postGoogleToken(token);
                savePrivate("rythm_response_" + i + ".json", exchange.body);
                writeExchangeSummary(i, exchange);
                if (exchange.status == 201) {
                    JSONObject body = new JSONObject(exchange.body);
                    if (body.has("token")) {
                        String rythmToken = body.getString("token");
                        savePrivate("rythm_token_" + i + ".secret", rythmToken);
                        put("account_" + i + "_rythm_token_len", Integer.toString(rythmToken.length()));
                        put("account_" + i + "_rythm_token_sha16", sha16(rythmToken));
                    }
                    writeFinalSummary(true, "rythm_status_201");
                    return;
                }
            } catch (Exception e) {
                put("account_" + i + "_token_error", e.getClass().getSimpleName() + ":" + safeMessage(e));
            }
        }

        writeFinalSummary(false, "exhausted_google_accounts");
    }

    private ExchangeResult postGoogleToken(String googleToken) {
        HttpURLConnection conn = null;
        ExchangeResult result = new ExchangeResult();
        try {
            URL url = new URL("https://login.rythm.co/google/");
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(15000);
            conn.setReadTimeout(15000);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("Accept", "application/json");
            byte[] body = new JSONObject().put("access_token", googleToken).toString().getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(body.length);
            OutputStream os = conn.getOutputStream();
            os.write(body);
            os.close();
            result.status = conn.getResponseCode();
            InputStream is = result.status >= 400 ? conn.getErrorStream() : conn.getInputStream();
            result.body = readAll(is);
        } catch (Exception e) {
            result.status = -1;
            result.body = "{\"error\":\"" + jsonEscape(e.getClass().getSimpleName() + ":" + safeMessage(e)) + "\"}";
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
        return result;
    }

    private void writeAccountsSummary(Account[] accounts) {
        try {
            JsonWriter writer = new JsonWriter(new FileWriter(new File(runDir, "accounts_summary.json")));
            writer.setIndent("  ");
            writer.beginObject();
            writer.name("count").value(accounts.length);
            writer.name("accounts").beginArray();
            for (int i = 0; i < accounts.length; i++) {
                writer.beginObject();
                writer.name("index").value(i);
                writer.name("type").value(accounts[i].type);
                writer.name("name_sha16").value(sha16(accounts[i].name));
                writer.endObject();
            }
            writer.endArray();
            writer.endObject();
            writer.close();
        } catch (Exception e) {
            put("accounts_summary_error", e.getClass().getSimpleName() + ":" + safeMessage(e));
        }
    }

    private void writeExchangeSummary(int index, ExchangeResult result) {
        try {
            JSONObject body = result.body.length() == 0 ? new JSONObject() : new JSONObject(result.body);
            List<String> keys = new ArrayList<String>();
            for (java.util.Iterator<String> it = body.keys(); it.hasNext();) {
                keys.add(it.next());
            }
            JsonWriter writer = new JsonWriter(new FileWriter(new File(runDir, "exchange_summary_" + index + ".json")));
            writer.setIndent("  ");
            writer.beginObject();
            writer.name("index").value(index);
            writer.name("status").value(result.status);
            writer.name("body_len").value(result.body.length());
            writer.name("body_sha16").value(sha16(result.body));
            writer.name("keys").beginArray();
            for (String key : keys) {
                writer.value(key);
            }
            writer.endArray();
            writer.name("has_token").value(body.has("token"));
            writer.name("has_user_id").value(body.has("user_id"));
            writer.endObject();
            writer.close();
            put("account_" + index + "_rythm_status", Integer.toString(result.status));
            put("account_" + index + "_rythm_keys", keys.toString());
            put("account_" + index + "_rythm_has_token", Boolean.toString(body.has("token")));
        } catch (Exception e) {
            put("exchange_summary_error", e.getClass().getSimpleName() + ":" + safeMessage(e));
        }
    }

    private void writeFinalSummary(boolean success, String reason) {
        try {
            JsonWriter writer = new JsonWriter(new FileWriter(new File(runDir, "final_summary.json")));
            writer.setIndent("  ");
            writer.beginObject();
            writer.name("success").value(success);
            writer.name("reason").value(reason);
            writer.endObject();
            writer.close();
        } catch (Exception e) {
            put("final_summary_error", e.getClass().getSimpleName() + ":" + safeMessage(e));
        }
        put("final_success", Boolean.toString(success));
        put("final_reason", reason);
    }

    private void savePrivate(String name, String value) {
        try {
            File file = new File(runDir, name);
            FileOutputStream out = new FileOutputStream(file);
            out.write(value.getBytes(StandardCharsets.UTF_8));
            out.close();
            file.setReadable(true, true);
            file.setWritable(true, true);
        } catch (Exception e) {
            put("save_error_" + name, e.getClass().getSimpleName() + ":" + safeMessage(e));
        }
    }

    private String readAll(InputStream is) throws Exception {
        if (is == null) {
            return "";
        }
        BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8));
        StringBuilder builder = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            builder.append(line);
        }
        reader.close();
        return builder.toString();
    }

    private void put(String key, String value) {
        status.putString(key, value == null ? "" : value);
    }

    private String sha16(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder();
            for (int i = 0; i < 8; i++) {
                builder.append(String.format(Locale.US, "%02x", bytes[i] & 0xff));
            }
            return builder.toString();
        } catch (Exception e) {
            return "";
        }
    }

    private String safeMessage(Exception e) {
        String msg = e.getMessage();
        return msg == null ? "" : msg;
    }

    private String jsonEscape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static class ExchangeResult {
        int status;
        String body = "";
    }
}
