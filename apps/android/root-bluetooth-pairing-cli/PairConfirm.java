import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.content.Context;
import android.os.Looper;
import android.os.SystemClock;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;

public final class PairConfirm {
    private static final int TRANSPORT_LE = 2;

    public static void main(String[] args) throws Exception {
        String address = args.length > 0 ? args[0] : "AA:BB:CC:DD:EE:50";
        String pin = args.length > 1 ? args[1] : "000000";
        long timeoutMs = args.length > 2 ? Long.parseLong(args[2]) : 30000L;

        BluetoothAdapter adapter = getAdapter();
        if (adapter == null) {
            System.out.println("no adapter");
            return;
        }
        BluetoothDevice device = adapter.getRemoteDevice(address);
        long deadline = SystemClock.elapsedRealtime() + timeoutMs;
        int lastState = -1;

        invokeBoolean(device, "cancelPairingUserInput");
        invokeCreateBond(device);

        while (SystemClock.elapsedRealtime() < deadline) {
            int state = device.getBondState();
            if (state != lastState) {
                System.out.println("bondState=" + state);
                lastState = state;
            }
            if (state == BluetoothDevice.BOND_BONDED) {
                System.out.println("bonded");
                return;
            }
            boolean pinOk = invokeSetPin(device, pin);
            boolean confirmOk = invokeSetPairingConfirmation(device);
            System.out.println("attempt pin=" + pinOk + " confirm=" + confirmOk + " state=" + state);
            SystemClock.sleep(150);
        }
        System.out.println("timeout state=" + device.getBondState());
    }

    private static boolean invokeCreateBond(BluetoothDevice device) {
        try {
            Method m = device.getClass().getMethod("createBond", int.class);
            Object result = m.invoke(device, TRANSPORT_LE);
            System.out.println("createBond(LE)=" + result);
            return Boolean.TRUE.equals(result);
        } catch (Throwable t) {
            System.out.println("createBond(LE) failed=" + t);
        }
        try {
            Method m = device.getClass().getMethod("createBond");
            Object result = m.invoke(device);
            System.out.println("createBond()=" + result);
            return Boolean.TRUE.equals(result);
        } catch (Throwable t) {
            System.out.println("createBond() failed=" + t);
            return false;
        }
    }

    private static boolean invokeSetPin(BluetoothDevice device, String pin) {
        try {
            Method m = device.getClass().getMethod("setPin", byte[].class);
            Object result = m.invoke(device, pin.getBytes(StandardCharsets.UTF_8));
            return Boolean.TRUE.equals(result);
        } catch (Throwable t) {
            return false;
        }
    }

    private static boolean invokeSetPairingConfirmation(BluetoothDevice device) {
        try {
            Method m = device.getClass().getMethod("setPairingConfirmation", boolean.class);
            Object result = m.invoke(device, true);
            return Boolean.TRUE.equals(result);
        } catch (Throwable t) {
            return false;
        }
    }

    private static boolean invokeBoolean(BluetoothDevice device, String method) {
        try {
            Method m = device.getClass().getMethod(method);
            Object result = m.invoke(device);
            System.out.println(method + "=" + result);
            return Boolean.TRUE.equals(result);
        } catch (Throwable t) {
            System.out.println(method + " failed=" + t);
            return false;
        }
    }

    private static BluetoothAdapter getAdapter() {
        try {
            BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
            if (adapter != null) {
                return adapter;
            }
        } catch (Throwable t) {
            System.out.println("getDefaultAdapter failed=" + t);
        }
        try {
            try {
                Looper.prepareMainLooper();
            } catch (Throwable ignored) {
            }
            Class<?> activityThreadClass = Class.forName("android.app.ActivityThread");
            Object activityThread = activityThreadClass.getMethod("systemMain").invoke(null);
            Context context = (Context) activityThreadClass.getMethod("getSystemContext").invoke(activityThread);
            System.out.println("context=" + context);
            BluetoothManager manager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
            System.out.println("manager=" + manager);
            BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
            if (adapter != null) {
                return adapter;
            }
            try {
                Object attributionSource = Context.class.getMethod("getAttributionSource").invoke(context);
                for (Method method : BluetoothAdapter.class.getDeclaredMethods()) {
                    if (!"createAdapter".equals(method.getName()) || method.getParameterTypes().length != 1) {
                        continue;
                    }
                    method.setAccessible(true);
                    Object result = method.invoke(null, attributionSource);
                    System.out.println("createAdapter(" + method.getParameterTypes()[0].getName() + ")=" + result);
                    if (result instanceof BluetoothAdapter) {
                        return (BluetoothAdapter) result;
                    }
                }
            } catch (Throwable t) {
                System.out.println("createAdapter reflection failed=" + t);
                Throwable cause = t.getCause();
                if (cause != null) {
                    System.out.println("createAdapter cause=" + cause);
                }
            }
            return null;
        } catch (Throwable t) {
            System.out.println("system context adapter failed=" + t);
            Throwable cause = t.getCause();
            if (cause != null) {
                System.out.println("system context adapter cause=" + cause);
            }
            return null;
        }
    }
}
