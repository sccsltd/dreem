package com.codex.dreemble;

import android.Manifest;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.method.ScrollingMovementMethod;
import android.view.Gravity;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.text.SimpleDateFormat;
import java.util.Arrays;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.UUID;
import java.lang.reflect.Method;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class MainActivity extends Activity {
    private static final String TAG = "DreemBleHelper";
    private static final String DEFAULT_ADDRESS = "AA:BB:CC:DD:EE:50";
    private static final byte[] AES_KEY = ascii("50755440496e2d32");
    private static final byte[] AES_IV = ascii("426c335f44654d33");
    private static final UUID CLIENT_CHARACTERISTIC_CONFIG_DESCRIPTOR_UUID =
            UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private static final int PAIRING_VARIANT_PASSKEY = 1;
    private static final int PAIRING_VARIANT_CONSENT = 3;
    private static final int PAIRING_VARIANT_DISPLAY_PASSKEY = 4;
    private static final int PAIRING_VARIANT_DISPLAY_PIN = 5;
    private static final int PAIRING_VARIANT_OOB_CONSENT = 6;
    private static final int PAIRING_VARIANT_PIN_16_DIGITS = 7;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ArrayDeque<Operation> queue = new ArrayDeque<Operation>();
    private final BluetoothGattCallback gattCallback = new GattCallbacks();
    private final BroadcastReceiver bondReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String action = intent.getAction();
            if (BluetoothDevice.ACTION_PAIRING_REQUEST.equals(action)) {
                handlePairingRequest(intent);
                return;
            }
            if (!BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(action)) {
                return;
            }
            BluetoothDevice device = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
            if (device == null || !targetAddress.equalsIgnoreCase(device.getAddress())) {
                return;
            }
            final BluetoothDevice target = device;
            int state = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.ERROR);
            int previous = intent.getIntExtra(BluetoothDevice.EXTRA_PREVIOUS_BOND_STATE, BluetoothDevice.ERROR);
            log("bond state " + bondStateName(previous) + " -> " + bondStateName(state));
            if (state == BluetoothDevice.BOND_BONDED) {
                finished = false;
                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        connectAfterBond(target);
                    }
                }, 750);
            } else if (state == BluetoothDevice.BOND_NONE && previous != BluetoothDevice.BOND_BONDING && removeBondFirst && removedBondThisRun && createBond) {
                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        requestBond(target);
                    }
                }, 750);
            } else if (state == BluetoothDevice.BOND_NONE && previous == BluetoothDevice.BOND_BONDING) {
                log("bond failed; continuing so fallback bond attempts can retry");
            }
        }
    };
    private final BluetoothAdapter.LeScanCallback scanCallback = new BluetoothAdapter.LeScanCallback() {
        @Override
        public void onLeScan(final BluetoothDevice device, int rssi, byte[] scanRecord) {
            String addr = device.getAddress();
            boolean addressMatched = targetAddress.equalsIgnoreCase(addr);
            // Avoid name lookups here; on Dreem they can trigger GAP reads before LE encryption completes.
            log("scan " + addr + " rssi=" + rssi + " name=<skipped>");
            if (addressMatched) {
                log("scan matched target");
                if (scanDetectOnly) {
                    return;
                }
                stopScan();
                connect(device);
            }
        }
    };

    private BluetoothAdapter adapter;
    private BluetoothGatt gatt;
    private Operation current;
    private TextView textView;
    private File logFile;
    private String targetAddress;
    private String userId;
    private String authUrl;
    private String apiUrl;
    private String serverPassword;
    private String ssid;
    private String wifiPassword;
    private String pairingPin;
    private String napConfJson;
    private String bondTransport;
    private String serverJsonOrder;
    private String wifiPayloadFormat;
    private String timezone;
    private int wifiSecurity;
    private int firmwareUpdateValue;
    private int notifyShortUuid;
    private int recordCommand;
    private int recordStopCommand;
    private int maxRetries;
    private long bondWaitMillis;
    private long directConnectDelayMillis;
    private long operationGapMillis;
    private long notifyMillis;
    private long recordWaitMillis;
    private long recordPostStopWaitMillis;
    private long keepAliveIntervalMillis;
    private long keepAliveMillis;
    private boolean readOnly;
    private boolean configureWifi;
    private boolean wifiOnly;
    private boolean wifiListOnly;
    private boolean serverOnly;
    private boolean serverPasswordOnly;
    private boolean statusOnly;
    private boolean timeOnly;
    private boolean reportOnly;
    private boolean recordOnly;
    private boolean keepAliveOnly;
    private boolean scanOnlyConnect;
    private boolean scanDetectOnly;
    private boolean syncNapConf;
    private boolean notifyOnly;
    private boolean captureLiveEeg;
    private boolean dumpAllReads;
    private boolean triggerFirmwareUpdate;
    private boolean createBond;
    private boolean removeBondFirst;
    private boolean skipUserId;
    private boolean skipServerReads;
    private boolean skipServerPasswordWrite;
    private boolean skipGattRefresh;
    private boolean skipMtuRequest;
    private String genericReadUuids;
    private String genericWriteUuid;
    private String genericWriteHex;
    private String genericNotifyUuid;
    private boolean genericNotifyBeforeWrite;
    private long genericNotifyMillis;
    private boolean pauseTouchpadAfterServer;
    private boolean primeAuthForWifi;
    private boolean removedBondThisRun;
    private boolean wroteWifi;
    private boolean serviceDiscoveryRequested;
    private boolean servicesReady;
    private boolean finished;
    private boolean bondReceiverRegistered;
    private boolean reconnecting;
    private boolean preserveQueueOnReconnect;
    private ByteArrayOutputStream notifyBuffer;
    private long notifyStartedAt;
    private int notifyPackets;
    private int retries;
    private int operationSerial;
    private int activeOperationSerial;
    private int serviceDiscoverySerial;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        textView = new TextView(this);
        textView.setTextSize(13);
        textView.setGravity(Gravity.START);
        textView.setPadding(18, 18, 18, 18);
        textView.setMovementMethod(new ScrollingMovementMethod());
        setContentView(textView);

        File dir = getExternalFilesDir(null);
        if (dir == null) {
            dir = getFilesDir();
        }
        logFile = new File(dir, "dreem_ble_helper.log");
        if (logFile.exists()) {
            logFile.delete();
        }

        readIntent(getIntent());
        log("start address=" + targetAddress + " readOnly=" + readOnly + " configureWifi=" + configureWifi + " wifiOnly=" + wifiOnly + " wifiListOnly=" + wifiListOnly + " serverOnly=" + serverOnly + " serverPasswordOnly=" + serverPasswordOnly + " statusOnly=" + statusOnly + " timeOnly=" + timeOnly + " reportOnly=" + reportOnly + " recordOnly=" + recordOnly + " keepAliveOnly=" + keepAliveOnly + " scanOnlyConnect=" + scanOnlyConnect + " scanDetectOnly=" + scanDetectOnly + " syncNapConf=" + syncNapConf + " notifyOnly=" + notifyOnly + " captureLiveEeg=" + captureLiveEeg + " dumpAllReads=" + dumpAllReads + " notifyUuid=0x" + Integer.toHexString(notifyShortUuid) + " notifyMillis=" + notifyMillis + " recordCommand=" + recordCommandName(recordCommand) + " recordStopCommand=" + recordCommandName(recordStopCommand) + " triggerFirmwareUpdate=" + triggerFirmwareUpdate + " createBond=" + createBond + " removeBondFirst=" + removeBondFirst + " skipUserId=" + skipUserId + " skipServerReads=" + skipServerReads + " skipServerPasswordWrite=" + skipServerPasswordWrite + " skipGattRefresh=" + skipGattRefresh + " skipMtuRequest=" + skipMtuRequest + " genericReadUuids=" + genericReadUuids + " genericWriteUuid=" + genericWriteUuid + " genericWriteHexLen=" + genericWriteHex.length() + " genericNotifyUuid=" + genericNotifyUuid + " genericNotifyBeforeWrite=" + genericNotifyBeforeWrite + " genericNotifyMillis=" + genericNotifyMillis + " pauseTouchpadAfterServer=" + pauseTouchpadAfterServer + " primeAuthForWifi=" + primeAuthForWifi + " bondTransport=" + bondTransport + " serverJsonOrder=" + serverJsonOrder + " wifiPayloadFormat=" + wifiPayloadFormat + " bondWaitMillis=" + bondWaitMillis + " directConnectDelayMillis=" + directConnectDelayMillis + " operationGapMillis=" + operationGapMillis + " recordWaitMillis=" + recordWaitMillis + " recordPostStopWaitMillis=" + recordPostStopWaitMillis + " keepAliveIntervalMillis=" + keepAliveIntervalMillis + " keepAliveMillis=" + keepAliveMillis + " maxRetries=" + maxRetries);
        log("logFile=" + logFile.getAbsolutePath());
        requestRuntimePermissions();
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                startBle();
            }
        }, 500);
    }

    @Override
    protected void onDestroy() {
        stopScan();
        if (gatt != null) {
            try {
                gatt.disconnect();
                gatt.close();
            } catch (Exception ignored) {
            }
            gatt = null;
        }
        if (bondReceiverRegistered) {
            try {
                unregisterReceiver(bondReceiver);
            } catch (Exception ignored) {
            }
            bondReceiverRegistered = false;
        }
        super.onDestroy();
    }

    private void readIntent(Intent intent) {
        targetAddress = getExtra(intent, "address", DEFAULT_ADDRESS);
        userId = getExtra(intent, "userId", "codex-" + System.currentTimeMillis());
        authUrl = getExtra(intent, "authUrl", "http://192.0.2.145:18081");
        apiUrl = getExtra(intent, "apiUrl", "http://192.0.2.145:18081/v1/dreem");
        serverPassword = getExtra(intent, "serverPassword", "changeme");
        ssid = getExtra(intent, "ssid", "");
        wifiPassword = getExtra(intent, "password", "");
        pairingPin = getExtra(intent, "pairingPin", "000000");
        napConfJson = getExtra(intent, "napConfJson", "");
        bondTransport = getExtra(intent, "bondTransport", "le").toLowerCase(Locale.US);
        serverJsonOrder = getExtra(intent, "serverJsonOrder", "api-first").toLowerCase(Locale.US);
        wifiPayloadFormat = getExtra(intent, "wifiPayloadFormat", "raw").toLowerCase(Locale.US);
        timezone = getExtra(intent, "timezone", TimeZone.getDefault().getID());
        wifiSecurity = intent.getIntExtra("security", 2);
        firmwareUpdateValue = intent.getIntExtra("firmwareUpdateValue", 0);
        recordCommand = intent.getIntExtra("recordCommand", -1);
        recordStopCommand = intent.getIntExtra("recordStopCommand", -1);
        notifyShortUuid = intent.getIntExtra("notifyUuid", 0xd301);
        maxRetries = intent.getIntExtra("maxRetries", 3);
        bondWaitMillis = intent.getLongExtra("bondWaitMillis", 60000L);
        directConnectDelayMillis = intent.getLongExtra("directConnectDelayMillis", 7000L);
        operationGapMillis = intent.getLongExtra("operationGapMillis", 500L);
        recordWaitMillis = intent.getLongExtra("recordWaitMillis", 0L);
        recordPostStopWaitMillis = intent.getLongExtra("recordPostStopWaitMillis", 10000L);
        keepAliveIntervalMillis = intent.getLongExtra("keepAliveIntervalMillis", 0L);
        keepAliveMillis = intent.getLongExtra("keepAliveMillis", 300000L);
        notifyMillis = intent.getLongExtra("notifyMillis", recordWaitMillis > 0 ? recordWaitMillis : 60000L);
        readOnly = intent.getBooleanExtra("readOnly", false);
        configureWifi = intent.getBooleanExtra("configureWifi", ssid.length() > 0);
        wifiOnly = intent.getBooleanExtra("wifiOnly", false);
        wifiListOnly = intent.getBooleanExtra("wifiListOnly", false);
        serverOnly = intent.getBooleanExtra("serverOnly", false);
        serverPasswordOnly = intent.getBooleanExtra("serverPasswordOnly", false);
        statusOnly = intent.getBooleanExtra("statusOnly", false);
        timeOnly = intent.getBooleanExtra("timeOnly", false);
        reportOnly = intent.getBooleanExtra("reportOnly", false);
        recordOnly = intent.getBooleanExtra("recordOnly", false);
        keepAliveOnly = intent.getBooleanExtra("keepAliveOnly", false);
        scanOnlyConnect = intent.getBooleanExtra("scanOnlyConnect", false);
        scanDetectOnly = intent.getBooleanExtra("scanDetectOnly", false);
        syncNapConf = intent.getBooleanExtra("syncNapConf", false);
        notifyOnly = intent.getBooleanExtra("notifyOnly", false) || intent.getBooleanExtra("liveEegOnly", false);
        captureLiveEeg = intent.getBooleanExtra("captureLiveEeg", false);
        dumpAllReads = intent.getBooleanExtra("dumpAllReads", false);
        triggerFirmwareUpdate = intent.getBooleanExtra("triggerFirmwareUpdate", false);
        createBond = intent.getBooleanExtra("createBond", false);
        removeBondFirst = intent.getBooleanExtra("removeBondFirst", false);
        skipUserId = intent.getBooleanExtra("skipUserId", false);
        skipServerReads = intent.getBooleanExtra("skipServerReads", false);
        skipServerPasswordWrite = intent.getBooleanExtra("skipServerPasswordWrite", false);
        skipGattRefresh = intent.getBooleanExtra("skipGattRefresh", false);
        skipMtuRequest = intent.getBooleanExtra("skipMtuRequest", false);
        genericReadUuids = getExtra(intent, "genericReadUuids", "");
        genericWriteUuid = getExtra(intent, "genericWriteUuid", "");
        genericWriteHex = getExtra(intent, "genericWriteHex", "");
        genericNotifyUuid = getExtra(intent, "genericNotifyUuid", "");
        genericNotifyBeforeWrite = intent.getBooleanExtra("genericNotifyBeforeWrite", false);
        genericNotifyMillis = intent.getLongExtra("genericNotifyMillis", 5000L);
        pauseTouchpadAfterServer = intent.getBooleanExtra("pauseTouchpadAfterServer", false);
        primeAuthForWifi = intent.getBooleanExtra("primeAuthForWifi", false);
    }

    private static String getExtra(Intent intent, String name, String fallback) {
        String value = intent.getStringExtra(name);
        return value == null ? fallback : value;
    }

    private static byte[] parseHexBytes(String value) {
        String clean = value == null ? "" : value.replaceAll("[^0-9A-Fa-f]", "");
        if ((clean.length() & 1) != 0) {
            throw new IllegalArgumentException("genericWriteHex must contain an even number of hex digits");
        }
        byte[] out = new byte[clean.length() / 2];
        for (int i = 0; i < out.length; i++) {
            int hi = Character.digit(clean.charAt(i * 2), 16);
            int lo = Character.digit(clean.charAt(i * 2 + 1), 16);
            if (hi < 0 || lo < 0) {
                throw new IllegalArgumentException("genericWriteHex contains non-hex data");
            }
            out[i] = (byte) ((hi << 4) | lo);
        }
        return out;
    }

    private void requestRuntimePermissions() {
        if (Build.VERSION.SDK_INT < 23) {
            return;
        }
        String[] permissions = new String[] {
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION,
                "android.permission.BLUETOOTH_SCAN",
                "android.permission.BLUETOOTH_CONNECT"
        };
        try {
            requestPermissions(permissions, 42);
        } catch (Throwable t) {
            log("permission request failed: " + t);
        }
    }

    private void startBle() {
        BluetoothManager manager = (BluetoothManager) getSystemService(Context.BLUETOOTH_SERVICE);
        if (manager == null) {
            log("no BluetoothManager");
            return;
        }
        adapter = manager.getAdapter();
        if (adapter == null) {
            log("no BluetoothAdapter");
            return;
        }
        if (!adapter.isEnabled()) {
            log("Bluetooth is disabled");
            return;
        }
        log("adapter ready; starting LE scan and direct connect fallback");
        startScan();
        if (keepAliveOnly || scanOnlyConnect) {
            scheduleKeepAliveScanRefresh();
        }
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (gatt == null) {
                    if (keepAliveOnly || scanOnlyConnect) {
                        log("scan-only connect mode; skipping direct connect fallback");
                        return;
                    }
                    log("direct connect fallback");
                    connect(adapter.getRemoteDevice(targetAddress));
                }
            }
        }, directConnectDelayMillis);
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (gatt == null) {
                    log("scan window elapsed with no connection");
                    if (keepAliveOnly || scanOnlyConnect) {
                        log("scan-only connect mode; leaving scan active");
                    } else {
                        stopScan();
                    }
                }
            }
        }, 20000);
    }

    private void scheduleKeepAliveScanRefresh() {
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (finished) {
                    return;
                }
                if (gatt == null) {
                    log("keepalive scan refresh");
                    stopScan();
                    startScan();
                }
                scheduleKeepAliveScanRefresh();
            }
        }, 30000);
    }

    private void startScan() {
        try {
            boolean ok = adapter.startLeScan(scanCallback);
            log("startLeScan ok=" + ok);
        } catch (Throwable t) {
            log("startLeScan failed: " + t);
        }
    }

    private void stopScan() {
        if (adapter == null) {
            return;
        }
        try {
            adapter.stopLeScan(scanCallback);
        } catch (Throwable ignored) {
        }
    }

    private void connect(BluetoothDevice device) {
        if (gatt != null) {
            return;
        }
        if (removeBondFirst && !removedBondThisRun && device.getBondState() != BluetoothDevice.BOND_NONE) {
            ensureBondReceiver();
            removedBondThisRun = true;
            removeBond(device);
            handler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    connect(adapter.getRemoteDevice(targetAddress));
                }
            }, 3000);
            return;
        }
        if (createBond) {
            ensureBondReceiver();
            int bondState = device.getBondState();
            log("bond requested; current=" + bondStateName(bondState));
            if (bondState == BluetoothDevice.BOND_BONDING) {
                log("waiting for active bond before GATT connect");
                return;
            }
            if (bondState != BluetoothDevice.BOND_BONDED) {
                requestBond(device);
                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        if (gatt == null) {
                            BluetoothDevice fallback = adapter.getRemoteDevice(targetAddress);
                            int state = fallback.getBondState();
                            log("bond wait elapsed; current=" + bondStateName(state));
                            if (state == BluetoothDevice.BOND_BONDED) {
                                connectAfterBond(fallback);
                            } else {
                                log("bond incomplete; protected write session will not start");
                                finished = true;
                            }
                        }
                    }
                }, bondWaitMillis);
                return;
            }
        }
        connectAfterBond(device);
    }

    private void requestBond(BluetoothDevice device) {
        try {
            if ("auto".equals(bondTransport)) {
                boolean ok = device.createBond();
                log("createBond(auto) ok=" + ok);
                return;
            }

            int transport = BluetoothDevice.TRANSPORT_LE;
            String transportName = "TRANSPORT_LE";
            if ("bredr".equals(bondTransport) || "br_edr".equals(bondTransport) || "classic".equals(bondTransport)) {
                transport = BluetoothDevice.TRANSPORT_BREDR;
                transportName = "TRANSPORT_BREDR";
            } else if (!"le".equals(bondTransport)) {
                log("unknown bondTransport=" + bondTransport + "; using TRANSPORT_LE");
            }

            try {
                Method createTransportBond = device.getClass().getMethod("createBond", int.class);
                boolean ok = (Boolean) createTransportBond.invoke(device, transport);
                log("createBond(" + transportName + ") ok=" + ok);
                return;
            } catch (NoSuchMethodException e) {
                log("createBond(" + transportName + ") unavailable; falling back");
            }
            boolean ok = device.createBond();
            log("createBond(auto fallback) ok=" + ok);
        } catch (Throwable t) {
            log("createBond failed: " + t);
        }
    }

    private void removeBond(BluetoothDevice device) {
        try {
            boolean ok = (Boolean) device.getClass().getMethod("removeBond").invoke(device);
            log("removeBond ok=" + ok);
        } catch (Throwable t) {
            log("removeBond failed: " + t);
        }
    }

    private void handlePairingRequest(Intent intent) {
        BluetoothDevice device = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
        if (device == null || !targetAddress.equalsIgnoreCase(device.getAddress())) {
            return;
        }
        int variant = intent.getIntExtra(BluetoothDevice.EXTRA_PAIRING_VARIANT, -1);
        int key = intent.getIntExtra(BluetoothDevice.EXTRA_PAIRING_KEY, -1);
        log("pairing request variant=" + pairingVariantName(variant) + " key=" + key);
        try {
            if (variant == BluetoothDevice.PAIRING_VARIANT_PIN
                    || variant == PAIRING_VARIANT_PIN_16_DIGITS) {
                boolean ok = device.setPin(pairingPin.getBytes("UTF-8"));
                log("setPin len=" + pairingPin.length() + " ok=" + ok);
            }
        } catch (Throwable t) {
            log("setPin failed: " + t);
        }
        try {
            boolean ok = device.setPairingConfirmation(true);
            log("setPairingConfirmation ok=" + ok);
        } catch (Throwable t) {
            log("setPairingConfirmation failed: " + t);
        }
    }

    private void connectAfterBond(BluetoothDevice device) {
        if (gatt != null) {
            return;
        }
        log("connect " + device.getAddress() + " bond=" + bondStateName(device.getBondState()));
        try {
            if (Build.VERSION.SDK_INT >= 23) {
                gatt = device.connectGatt(this, false, gattCallback, BluetoothDevice.TRANSPORT_LE);
            } else {
                gatt = device.connectGatt(this, false, gattCallback);
            }
        } catch (Throwable t) {
            log("connectGatt failed: " + t);
            gatt = null;
        }
    }

    private void ensureBondReceiver() {
        if (bondReceiverRegistered) {
            return;
        }
        try {
            IntentFilter filter = new IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
            filter.addAction(BluetoothDevice.ACTION_PAIRING_REQUEST);
            filter.setPriority(1000);
            registerReceiver(bondReceiver, filter);
            bondReceiverRegistered = true;
            log("bond receiver registered");
        } catch (Throwable t) {
            log("bond receiver registration failed: " + t);
        }
    }

    private String bondStateName(int state) {
        switch (state) {
            case BluetoothDevice.BOND_NONE:
                return "BOND_NONE";
            case BluetoothDevice.BOND_BONDING:
                return "BOND_BONDING";
            case BluetoothDevice.BOND_BONDED:
                return "BOND_BONDED";
            case BluetoothDevice.ERROR:
                return "ERROR";
            default:
                return String.valueOf(state);
        }
    }

    private String pairingVariantName(int variant) {
        switch (variant) {
            case BluetoothDevice.PAIRING_VARIANT_PIN:
                return "PIN";
            case PAIRING_VARIANT_PASSKEY:
                return "PASSKEY";
            case BluetoothDevice.PAIRING_VARIANT_PASSKEY_CONFIRMATION:
                return "PASSKEY_CONFIRMATION";
            case PAIRING_VARIANT_CONSENT:
                return "CONSENT";
            case PAIRING_VARIANT_DISPLAY_PASSKEY:
                return "DISPLAY_PASSKEY";
            case PAIRING_VARIANT_DISPLAY_PIN:
                return "DISPLAY_PIN";
            case PAIRING_VARIANT_OOB_CONSENT:
                return "OOB_CONSENT";
            case PAIRING_VARIANT_PIN_16_DIGITS:
                return "PIN_16_DIGITS";
            default:
                return String.valueOf(variant);
        }
    }

    private void retryConnect() {
        if (finished) {
            log("retry skipped; queue already finished");
            return;
        }
        if (retries >= maxRetries) {
            log("giving up after retries");
            return;
        }
        retries++;
        reconnecting = true;
        activeOperationSerial++;
        closeGatt(!preserveQueueOnReconnect);
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (finished) {
                    log("retry skipped; queue already finished");
                    return;
                }
                log("retry " + retries);
                startScan();
                if (keepAliveOnly || scanOnlyConnect) {
                    log("scan-only connect mode; retry is scan-only");
                    return;
                }
                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        if (gatt == null) {
                            connect(adapter.getRemoteDevice(targetAddress));
                        }
                    }
                }, 5000);
            }
        }, 1500);
    }

    private void retryConnectPreservingQueue(String reason) {
        log("retry preserving queue reason=" + reason + " current=" + (current == null ? "none" : current.name) + " queued=" + queue.size());
        if (current != null) {
            current.resetForRetry();
            queue.addFirst(current);
            current = null;
        }
        preserveQueueOnReconnect = true;
        retryConnect();
    }

    private void closeGatt() {
        closeGatt(true);
    }

    private void closeGatt(boolean clearQueue) {
        serviceDiscoveryRequested = false;
        servicesReady = false;
        serviceDiscoverySerial++;
        current = null;
        if (clearQueue) {
            queue.clear();
        }
        if (gatt != null) {
            try {
                gatt.close();
            } catch (Exception ignored) {
            }
            gatt = null;
        }
    }

    private void discover() {
        if (gatt == null) {
            return;
        }
        if (skipGattRefresh) {
            log("gatt refresh skipped");
            discoverAfterRefresh();
            return;
        }
        refreshGatt();
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                discoverAfterRefresh();
            }
        }, 500);
    }

    private void discoverAfterRefresh() {
        if (gatt == null) {
            return;
        }
        try {
            gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH);
        } catch (Throwable ignored) {
        }
        if (skipMtuRequest) {
            log("requestMtu skipped");
            handler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    requestDiscoverServices("mtu skipped");
                }
            }, 300);
            return;
        }
        if (Build.VERSION.SDK_INT >= 21) {
            try {
                boolean mtu = gatt.requestMtu(185);
                log("requestMtu ok=" + mtu);
                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        requestDiscoverServices("mtu fallback");
                    }
                }, 1500);
                return;
            } catch (Throwable t) {
                log("requestMtu failed: " + t);
            }
        }
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                requestDiscoverServices("no mtu delayed");
            }
        }, 300);
    }

    private void refreshGatt() {
        if (gatt == null) {
            return;
        }
        try {
            Method method = gatt.getClass().getMethod("refresh");
            Object result = method.invoke(gatt);
            log("gatt refresh result=" + result);
        } catch (Throwable t) {
            log("gatt refresh failed: " + t.getClass().getSimpleName() + ": " + t.getMessage());
        }
    }

    private void requestDiscoverServices(String reason) {
        if (gatt == null || servicesReady || serviceDiscoveryRequested) {
            log("discoverServices skipped reason=" + reason + " requested=" + serviceDiscoveryRequested + " ready=" + servicesReady);
            return;
        }
        serviceDiscoveryRequested = true;
        final int serial = ++serviceDiscoverySerial;
        boolean ok = gatt.discoverServices();
        log("discoverServices reason=" + reason + " ok=" + ok);
        if (ok) {
            handler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (gatt != null && serviceDiscoveryRequested && !servicesReady && serviceDiscoverySerial == serial) {
                        log("discoverServices timeout; retrying");
                        serviceDiscoveryRequested = false;
                        requestDiscoverServices("timeout retry");
                    }
                }
            }, 7000);
        }
    }

    private void dumpServices() {
        List<BluetoothGattService> services = gatt.getServices();
        log("services=" + services.size());
        for (BluetoothGattService service : services) {
            log("service " + service.getUuid());
            List<BluetoothGattCharacteristic> chars = service.getCharacteristics();
            for (BluetoothGattCharacteristic ch : chars) {
                log("  char " + ch.getUuid() + " short=0x" + Integer.toHexString(shortUuidFromUuid(ch.getUuid()))
                        + " props=" + characteristicProperties(ch));
            }
        }
        int[] known = new int[] {
                0xd003, 0xd007,
                0xd011, 0xd012, 0xd013,
                0xd701, 0xd702, 0xd703, 0xd704, 0xd705, 0xd706, 0xd707, 0xd708, 0xd709,
                0xd201, 0xd202, 0xd203, 0xd204, 0xd208, 0xd209, 0xd210, 0xd211,
                0xd301, 0xd302, 0xd304, 0xd305, 0xd306, 0xd307, 0xd308, 0xd309, 0xd30a, 0xd30b,
                0xd501, 0xd504, 0xd505, 0xd506, 0xd508, 0xd509, 0xd510, 0xd511, 0xd512, 0xd513,
                0xd514, 0xd515, 0xd516, 0xd517, 0xd518, 0xd852, 0xd853,
                0xd801, 0xd803, 0xd804, 0xd805,
                0xda01, 0xda02, 0xda03, 0xda04, 0xda05,
                0xd904, 0xd903, 0xd103, 0xd102, 0xd101, 0xd401, 0xd402, 0xd951, 0xd952,
                0xd905, 0xd901, 0xd601, 0xd902
        };
        StringBuilder sb = new StringBuilder("known=");
        for (int i = 0; i < known.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            BluetoothGattCharacteristic ch = findCharacteristic(known[i]);
            sb.append(Integer.toHexString(known[i])).append(ch == null ? ":missing" : ":ok:" + characteristicProperties(ch));
        }
        log(sb.toString());
    }

    private void buildOperations() {
        queue.clear();
        if (genericReadUuids.length() > 0 || genericNotifyUuid.length() > 0 || genericWriteUuid.length() > 0) {
            for (String value : genericReadUuids.split(",")) {
                String trimmed = value.trim();
                if (trimmed.length() > 0) {
                    enqueueReadUuid(UUID.fromString(trimmed), "genericRead-" + trimmed, false);
                }
            }
            if (genericNotifyBeforeWrite && genericNotifyUuid.length() > 0 && genericWriteUuid.length() > 0) {
                enqueueSubscribeUuid(UUID.fromString(genericNotifyUuid), "genericSubscribe-" + genericNotifyUuid);
            } else if (genericNotifyUuid.length() > 0) {
                enqueueNotifyUuid(UUID.fromString(genericNotifyUuid), "genericNotify-" + genericNotifyUuid, genericNotifyMillis);
            }
            if (genericWriteUuid.length() > 0) {
                if (readOnly) {
                    log("generic write skipped because readOnly=true");
                } else {
                    enqueueWriteUuid(UUID.fromString(genericWriteUuid), "genericWrite-" + genericWriteUuid, parseHexBytes(genericWriteHex));
                    if (genericNotifyBeforeWrite && genericNotifyUuid.length() > 0) {
                        enqueueDelay("genericNotifyWait", genericNotifyMillis);
                    }
                }
            }
            return;
        }
        if (dumpAllReads) {
            enqueueRead(0xd003, "unknownD003", false);
            enqueueRead(0xd007, "unknownD007", false);
            enqueueRead(0xd701, "firmwareRealVersion", false);
            enqueueRead(0xd702, "appCompatibility", false);
            enqueueRead(0xd704, "firmwareStatus", false);
            enqueueRead(0xd705, "firmwareRootVersion", false);
            enqueueRead(0xd708, "environment/version", true);
            enqueueRead(0xd709, "hardwareVersion", false);
            enqueueRead(0xd201, "unknownD201", false);
            enqueueRead(0xd202, "unknownD202", false);
            enqueueRead(0xd203, "batteryLevel", false);
            enqueueRead(0xd204, "isPlugged", false);
            enqueueRead(0xd208, "healthErrorStatus", false);
            enqueueRead(0xd209, "healthNotifyReadable", false);
            enqueueRead(0xd211, "batteryDetail", false);
            enqueueRead(0xd013, "touchpadStatus", false);
            enqueueRead(0xd301, "liveEegReadable", false);
            enqueueRead(0xd304, "recordStatus", false);
            enqueueRead(0xd305, "heartRate", false);
            enqueueRead(0xd306, "signalQuality", false);
            enqueueRead(0xd307, "nightConf", false);
            enqueueRead(0xd308, "nightConfStatus", false);
            enqueueRead(0xd309, "currentRecordUuid", false);
            enqueueRead(0xd30b, "recordAlgoStatus", false);
            enqueueRead(0xd501, "soundContent", false);
            enqueueRead(0xd508, "soundSelected", false);
            enqueueRead(0xd509, "soundLongList", false);
            enqueueRead(0xd512, "soundParamD512", false);
            enqueueRead(0xd513, "soundParamD513", false);
            enqueueRead(0xd514, "soundParamD514", false);
            enqueueRead(0xd515, "soundParamD515", false);
            enqueueRead(0xd516, "soundParamD516", false);
            enqueueRead(0xd517, "soundParamD517", false);
            enqueueRead(0xd852, "unknownD852", false);
            enqueueRead(0xd803, "alarmConf", false);
            enqueueRead(0xd805, "alarmLongConf", false);
            enqueueRead(0xda02, "relaxLatestUuid", false);
            enqueueRead(0xda03, "relaxLatestReport", false);
            enqueueRead(0xda05, "relaxStatus", false);
            enqueueRead(0xd904, "isServerPasswordRequired", true);
            enqueueRead(0xd903, "headbandMac", false);
            enqueueRead(0xd103, "wifiConfig", true);
            enqueueRead(0xd102, "wifiStatus", false);
            enqueueRead(0xd101, "wifiList", true);
            enqueueRead(0xd401, "latestReportUuid", false);
            enqueueRead(0xd402, "latestReport", false);
            enqueueRead(0xd952, "latestPharmaReportUuid", false);
            enqueueRead(0xd951, "latestPharmaReport", false);
            return;
        }
        if (notifyOnly) {
            enqueueRead(0xd204, "isPlugged", false);
            enqueueRead(0xd304, "recordStatus", false);
            enqueueRead(0xd306, "signalQuality", false);
            enqueueNotify(notifyShortUuid, "notify-" + Integer.toHexString(notifyShortUuid), notifyMillis);
            enqueueRead(0xd306, "signalQualityAfterNotify", false);
            return;
        }
        if (statusOnly) {
            enqueueRead(0xd203, "batteryLevel", false);
            enqueueRead(0xd204, "isPlugged", false);
            enqueueRead(0xd208, "healthErrorStatus", false);
            enqueueRead(0xd304, "recordStatus", false);
            enqueueRead(0xd305, "heartRate", false);
            enqueueRead(0xd306, "signalQuality", false);
            enqueueRead(0xd308, "nightConfStatus", false);
            enqueueRead(0xd309, "currentRecordUuid", false);
            enqueueRead(0xd401, "latestReportUuid", false);
            return;
        }
        if (timeOnly) {
            enqueueWrite(0xd601, "setTime", timePayload());
            return;
        }
        if (reportOnly) {
            enqueueRead(0xd401, "latestReportUuid", false);
            enqueueRead(0xd402, "latestReport", false);
            enqueueRead(0xd952, "latestPharmaReportUuid", false);
            enqueueRead(0xd951, "latestPharmaReport", false);
            return;
        }
        if (keepAliveOnly) {
            enqueueRead(0xd203, "batteryLevel", false);
            enqueueRead(0xd204, "isPlugged", false);
            enqueueRead(0xd208, "healthErrorStatus", false);
            enqueueRead(0xd304, "recordStatus", false);
            enqueueRead(0xd306, "signalQuality", false);
            enqueueRead(0xd309, "currentRecordUuid", false);
            enqueueRead(0xd401, "latestReportUuid", false);
            enqueueKeepAliveWait("idleKeepAlive", keepAliveMillis);
            enqueueRead(0xd203, "batteryLevelAfterKeepAlive", false);
            enqueueRead(0xd304, "recordStatusAfterKeepAlive", false);
            enqueueRead(0xd309, "currentRecordUuidAfterKeepAlive", false);
            enqueueRead(0xd401, "latestReportUuidAfterKeepAlive", false);
            return;
        }
        if (recordOnly) {
            enqueueRead(0xd204, "isPlugged", false);
            enqueueRead(0xd304, "recordStatus", false);
            enqueueRead(0xd309, "currentRecordUuid", false);
            enqueueRead(0xd401, "latestReportUuid", false);
            if (!readOnly && recordCommand >= 0) {
                if (syncNapConf && recordCommand == 3) {
                    String json = napConfJson.length() > 0 ? napConfJson : defaultNapConfJson();
                    log("queue setNapConf bytes=" + utf8(json).length);
                    enqueueWrite(0xd30a, "setNapConf", lengthPrefixed(json));
                    enqueueDelay("settleAfterNapConf", 1000L);
                }
                enqueueWrite(0xd302, "manageRecord-" + recordCommandName(recordCommand), intPayload(recordCommand));
                if (captureLiveEeg) {
                    enqueueDelay("settleAfterRecordCommand", 2000L);
                    enqueueRead(0xd304, "recordStatusAfterCommand", false);
                    enqueueRead(0xd309, "currentRecordUuidAfterCommand", false);
                    enqueueNotify(0xd301, "liveEegDuringRecord", notifyMillis);
                } else if (recordWaitMillis > 0) {
                    enqueueKeepAliveWait("recordWaitKeepAlive", recordWaitMillis);
                }
                if (!captureLiveEeg) {
                    enqueueRead(0xd304, "recordStatusAfterCommand", false);
                    enqueueRead(0xd309, "currentRecordUuidAfterCommand", false);
                }
                if (recordStopCommand >= 0) {
                    enqueueWrite(0xd302, "manageRecord-" + recordCommandName(recordStopCommand), intPayload(recordStopCommand));
                    if (recordPostStopWaitMillis > 0) {
                        enqueueKeepAliveWait("postStopKeepAlive", recordPostStopWaitMillis);
                    }
                    enqueueRead(0xd304, "recordStatusAfterStop", false);
                    enqueueRead(0xd309, "currentRecordUuidAfterStop", false);
                    enqueueRead(0xd401, "latestReportUuidAfterStop", false);
                    enqueueRead(0xd402, "latestReportAfterStop", false);
                    enqueueRead(0xd952, "latestPharmaReportUuidAfterStop", false);
                    enqueueRead(0xd951, "latestPharmaReportAfterStop", false);
                }
            } else if (!readOnly && recordStopCommand >= 0) {
                enqueueWrite(0xd302, "manageRecord-" + recordCommandName(recordStopCommand), intPayload(recordStopCommand));
                if (recordPostStopWaitMillis > 0) {
                    enqueueKeepAliveWait("postStopKeepAlive", recordPostStopWaitMillis);
                }
                enqueueRead(0xd304, "recordStatusAfterStop", false);
                enqueueRead(0xd309, "currentRecordUuidAfterStop", false);
                enqueueRead(0xd401, "latestReportUuidAfterStop", false);
                enqueueRead(0xd402, "latestReportAfterStop", false);
                enqueueRead(0xd952, "latestPharmaReportUuidAfterStop", false);
                enqueueRead(0xd951, "latestPharmaReportAfterStop", false);
            }
            return;
        }
        if (wifiOnly) {
            if (wifiListOnly) {
                enqueueRead(0xd101, "wifiList", true);
                return;
            }
            if (primeAuthForWifi && !readOnly) {
                if (!skipUserId) {
                    enqueueWrite(0xd901, "setUserId", utf8(userId));
                }
                enqueueWrite(0xd601, "setTime", timePayload());
            }
            if (configureWifi && ssid.length() > 0) {
                enqueueWrite(0xd102, "setWifiAuth", aesEncrypt(wifiPayload()));
                enqueueDelay("waitForWifiConfig", 15000);
                wroteWifi = true;
            }
            enqueueRead(0xd102, configureWifi ? "wifiStatusAfterWrite" : "wifiStatus", false);
            enqueueRead(0xd103, configureWifi ? "wifiConfigAfterWrite" : "wifiConfig", true);
            enqueueRead(0xd101, "wifiList", true);
            return;
        }
        if (serverOnly) {
            if (!skipServerReads) {
                enqueueRead(0xd904, "isServerPasswordRequired", true);
                enqueueRead(0xd903, "headbandMac", false);
            }
            if (!readOnly) {
                if (!skipUserId) {
                    enqueueWrite(0xd901, "setUserId", utf8(userId));
                }
                enqueueWrite(0xd601, "setTime", timePayload());
                enqueueWrite(0xd902, "setServerUrls", lengthPrefixed(serverJson()));
                if (pauseTouchpadAfterServer) {
                    enqueueWrite(0xd011, "pauseTouchpadTemporary(false)", booleanPayload(false));
                }
                if (!skipServerReads) {
                    enqueueRead(0xd904, "isServerPasswordRequiredAfterUrls", true);
                }
                if (!skipServerPasswordWrite) {
                    enqueueWrite(0xd905, "setServerPassword", aesEncrypt(utf8(serverPassword)));
                    enqueueDelay("waitAfterServerPassword", 1500);
                    if (!skipServerReads) {
                        enqueueRead(0xd904, "isServerPasswordRequiredAfterPassword", true);
                    }
                }
            }
            return;
        }
        if (serverPasswordOnly) {
            enqueueRead(0xd904, "isServerPasswordRequired", true);
            if (!readOnly) {
                enqueueWrite(0xd905, "setServerPasswordOnly", aesEncrypt(utf8(serverPassword)));
                enqueueDelay("waitAfterServerPasswordOnly", 1500);
                enqueueRead(0xd904, "isServerPasswordRequiredAfterPasswordOnly", true);
            }
            return;
        }
        enqueueRead(0xd708, "environment/version", true);
        enqueueRead(0xd701, "firmwareRealVersion", false);
        enqueueRead(0xd705, "firmwareRootVersion", false);
        enqueueRead(0xd702, "appCompatibility", false);
        enqueueRead(0xd709, "hardwareVersion", false);
        enqueueRead(0xd904, "isServerPasswordRequired", true);
        enqueueRead(0xd903, "headbandMac", false);
        enqueueRead(0xd103, "wifiConfig", true);
        enqueueRead(0xd102, "wifiStatus", false);
        enqueueRead(0xd101, "wifiList", true);
        enqueueRead(0xd401, "latestReportUuid", false);
        enqueueRead(0xd402, "latestReport", false);
        enqueueRead(0xd952, "latestPharmaReportUuid", false);
        enqueueRead(0xd951, "latestPharmaReport", false);

        if (!readOnly) {
            enqueueWrite(0xd901, "setUserId", utf8(userId));
            enqueueWrite(0xd601, "setTime", timePayload());
            enqueueWrite(0xd902, "setServerUrls", lengthPrefixed(serverJson()));
            if (pauseTouchpadAfterServer) {
                enqueueWrite(0xd011, "pauseTouchpadTemporary(false)", booleanPayload(false));
            }
            enqueueRead(0xd904, "isServerPasswordRequiredAfterUrls", true);
            if (!skipServerPasswordWrite) {
                enqueueWrite(0xd905, "setServerPassword", aesEncrypt(utf8(serverPassword)));
                enqueueDelay("waitAfterServerPassword", 1500);
            }
            if (configureWifi && ssid.length() > 0) {
                enqueueWrite(0xd102, "setWifiAuth", aesEncrypt(wifiPayload()));
                enqueueDelay("waitForWifiConfig", 15000);
                enqueueRead(0xd102, "wifiStatusAfterWrite", false);
                enqueueRead(0xd103, "wifiConfigAfterWrite", true);
                wroteWifi = true;
            }
        }
        if (triggerFirmwareUpdate) {
            enqueueWrite(0xd706, "startFirmwareUpdate", firmwareUpdatePayload(firmwareUpdateValue));
            enqueueDelay("waitAfterFirmwareUpdateTrigger", 30000);
            enqueueRead(0xd701, "firmwareRealVersionAfterTrigger", false);
            enqueueRead(0xd705, "firmwareRootVersionAfterTrigger", false);
        }
    }

    private void enqueueRead(int shortUuid, String name, boolean tryDecrypt) {
        queue.add(Operation.read(shortUuid, name, tryDecrypt));
    }

    private void enqueueReadUuid(UUID uuid, String name, boolean tryDecrypt) {
        queue.add(Operation.readUuid(uuid, name, tryDecrypt));
    }

    private void enqueueWrite(int shortUuid, String name, byte[] payload) {
        queue.add(Operation.write(shortUuid, name, payload));
    }

    private void enqueueWriteUuid(UUID uuid, String name, byte[] payload) {
        queue.add(Operation.writeUuid(uuid, name, payload));
    }

    private void enqueueNotify(int shortUuid, String name, long millis) {
        queue.add(Operation.notify(shortUuid, name, Math.max(1000L, millis)));
    }

    private void enqueueNotifyUuid(UUID uuid, String name, long millis) {
        queue.add(Operation.notifyUuid(uuid, name, Math.max(1000L, millis)));
    }

    private void enqueueSubscribeUuid(UUID uuid, String name) {
        queue.add(Operation.subscribeUuid(uuid, name));
    }

    private void enqueueDelay(String name, long millis) {
        queue.add(Operation.delay(name, millis));
    }

    private void enqueueKeepAliveWait(String name, long totalMillis) {
        if (totalMillis <= 0) {
            return;
        }
        if (keepAliveIntervalMillis <= 0) {
            enqueueDelay(name, totalMillis);
            return;
        }
        long remaining = totalMillis;
        int index = 1;
        while (remaining > 0) {
            long chunk = Math.min(keepAliveIntervalMillis, remaining);
            enqueueDelay(name + "-delay-" + index, chunk);
            enqueueRead(0xd304, name + "-recordStatus-" + index, false);
            enqueueRead(0xd309, name + "-currentRecordUuid-" + index, false);
            enqueueRead(0xd306, name + "-signalQuality-" + index, false);
            if (index == 1 || index % 4 == 0 || remaining == chunk) {
                enqueueRead(0xd203, name + "-batteryLevel-" + index, false);
            }
            remaining -= chunk;
            index++;
        }
    }

    private void startNextOperation() {
        current = queue.poll();
        if (current == null) {
            if (reconnecting) {
                log("operation queue empty during reconnect; waiting for fresh services");
                return;
            }
            finished = true;
            log("operation queue complete wroteWifi=" + wroteWifi);
            return;
        }
        if (current.kind == Operation.KIND_DELAY) {
            activeOperationSerial = ++operationSerial;
            final Operation delayOp = current;
            final int delaySerial = activeOperationSerial;
            log("delay " + delayOp.name + " " + delayOp.delayMillis + "ms");
            handler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (current == delayOp && activeOperationSerial == delaySerial) {
                        current = null;
                        startNextOperation();
                    }
                }
            }, delayOp.delayMillis);
            return;
        }
        if (current.kind == Operation.KIND_NOTIFY) {
            activeOperationSerial = ++operationSerial;
            startNotifyOperation(current, activeOperationSerial);
            return;
        }
        if (current.kind == Operation.KIND_SUBSCRIBE) {
            activeOperationSerial = ++operationSerial;
            startNotifyOperation(current, activeOperationSerial);
            return;
        }

        BluetoothGattCharacteristic ch = findCharacteristic(current);
        if (ch == null) {
            log("missing " + current.name + " " + operationUuid(current));
            current = null;
            handler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    startNextOperation();
                }
            }, 250);
            return;
        }

        activeOperationSerial = ++operationSerial;
        final int serial = activeOperationSerial;
        final Operation timeoutOp = current;
        if (current.kind == Operation.KIND_READ) {
            boolean ok = gatt.readCharacteristic(ch);
            log("read " + current.name + " " + operationUuid(current) + " ok=" + ok);
            if (!ok) {
                retryConnectPreservingQueue("read start failed " + current.name);
                return;
            }
        } else {
            int props = ch.getProperties();
            int writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT;
            boolean writeWithResponse = (props & BluetoothGattCharacteristic.PROPERTY_WRITE) != 0;
            boolean writeNoResponse = (props & BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE) != 0;
            if (!writeWithResponse && writeNoResponse) {
                writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE;
            }
            ch.setWriteType(writeType);
            ch.setValue(current.payload);
            boolean ok = gatt.writeCharacteristic(ch);
            log("write " + current.name + " " + operationUuid(current) + " len=" + current.payload.length + " props=" + characteristicProperties(ch) + " writeType=" + writeType + " ok=" + ok);
            if (!ok) {
                retryConnectPreservingQueue("write start failed " + current.name);
                return;
            }
            if (ok && writeType == BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) {
                final Operation noResponseOp = current;
                final int noResponseSerial = activeOperationSerial;
                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        if (current == noResponseOp && activeOperationSerial == noResponseSerial) {
                            log("writeNoResponse sent " + noResponseOp.name);
                            current = null;
                            startNextOperation();
                        }
                    }
                }, 500);
            }
        }
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (current == timeoutOp && activeOperationSerial == serial) {
                    log("operation timeout " + current.name);
                    retryConnectPreservingQueue("operation timeout " + current.name);
                }
            }
        }, operationTimeoutMillis(timeoutOp));
    }

    private long operationTimeoutMillis(Operation op) {
        if (op.kind == Operation.KIND_WRITE && op.shortUuid == 0xd102) {
            return 30000L;
        }
        if (op.kind == Operation.KIND_READ
                && (op.shortUuid == 0xd402 || op.shortUuid == 0xd951 || op.shortUuid == 0xda03)) {
            return 600000L;
        }
        if (op.kind == Operation.KIND_READ && op.shortUuid == 0xd003) {
            return 30000L;
        }
        if (op.kind == Operation.KIND_READ && (op.shortUuid == 0xd509 || op.shortUuid == 0xd805)) {
            return 60000L;
        }
        return 10000L;
    }

    private void startNotifyOperation(final Operation op, final int serial) {
        BluetoothGattCharacteristic ch = findCharacteristic(op);
        if (ch == null) {
            log("missing notify " + op.name + " " + operationUuid(op));
            current = null;
            handler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    startNextOperation();
                }
            }, 250);
            return;
        }
        notifyBuffer = new ByteArrayOutputStream();
        notifyStartedAt = System.currentTimeMillis();
        notifyPackets = 0;
        boolean localOk = gatt.setCharacteristicNotification(ch, true);
        BluetoothGattDescriptor descriptor = ch.getDescriptor(CLIENT_CHARACTERISTIC_CONFIG_DESCRIPTOR_UUID);
        log("notifyEnable " + op.name + " " + operationUuid(op) + " localOk=" + localOk + " descriptor=" + (descriptor != null));
        if (descriptor == null) {
            finishNotifyOperation(op);
            return;
        }
        descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
        boolean ok = gatt.writeDescriptor(descriptor);
        log("descriptorWrite enable " + op.name + " ok=" + ok);
        if (!ok) {
            finishNotifyOperation(op);
            return;
        }
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (current == op && activeOperationSerial == serial && !op.notifyCaptureStarted) {
                    log("notify descriptor timeout " + op.name);
                    finishNotifyOperation(op);
                }
            }
        }, 15000L);
    }

    private void beginNotifyCapture(final Operation op) {
        if (op.notifyCaptureStarted) {
            return;
        }
        op.notifyCaptureStarted = true;
        notifyStartedAt = System.currentTimeMillis();
        log("notifyCapture start " + op.name + " " + op.delayMillis + "ms");
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (current == op) {
                    finishNotifyOperation(op);
                }
            }
        }, op.delayMillis);
    }

    private void finishNotifyOperation(Operation op) {
        if (gatt != null) {
            BluetoothGattCharacteristic ch = findCharacteristic(op);
            if (ch != null) {
                try {
                    gatt.setCharacteristicNotification(ch, false);
                } catch (Throwable ignored) {
                }
            }
        }
        byte[] payload = notifyBuffer == null ? new byte[0] : notifyBuffer.toByteArray();
        long elapsed = Math.max(0L, System.currentTimeMillis() - notifyStartedAt);
        log("notifyResult " + op.name + " packets=" + notifyPackets + " bytes=" + payload.length + " elapsedMs=" + elapsed);
        savePayload(op.name + "_framed", payload);
        notifyBuffer = null;
        notifyPackets = 0;
        current = null;
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                startNextOperation();
            }
        }, operationGapMillis);
    }

    private void onNotify(BluetoothGattCharacteristic ch) {
        byte[] value = ch.getValue();
        int shortUuid = shortUuidFromUuid(ch.getUuid());
        Operation op = current;
        if (op == null || op.kind != Operation.KIND_NOTIFY || !operationMatchesCharacteristic(op, ch)) {
            log("notifyLate " + ch.getUuid() + " len=" + (value == null ? 0 : value.length) + " hex=" + hex(value, 48));
            return;
        }
        if (value == null) {
            value = new byte[0];
        }
        notifyPackets++;
        writeNotifyPacket(value);
        if (notifyPackets <= 20 || notifyPackets % 100 == 0) {
            log("notifyPacket " + op.name + " #" + notifyPackets + " len=" + value.length + " hex=" + hex(value, 64) + decodeLiveEeg(value));
        }
    }

    private void writeNotifyPacket(byte[] value) {
        if (notifyBuffer == null) {
            return;
        }
        int elapsed = (int) Math.min(Integer.MAX_VALUE, Math.max(0L, System.currentTimeMillis() - notifyStartedAt));
        byte[] header = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN)
                .putInt(elapsed)
                .putInt(value.length)
                .array();
        notifyBuffer.write(header, 0, header.length);
        notifyBuffer.write(value, 0, value.length);
    }

    private BluetoothGattCharacteristic findCharacteristic(int shortUuid) {
        UUID uuid = uuid16(shortUuid);
        for (BluetoothGattService service : gatt.getServices()) {
            BluetoothGattCharacteristic ch = service.getCharacteristic(uuid);
            if (ch != null) {
                return ch;
            }
        }
        return null;
    }

    private BluetoothGattCharacteristic findCharacteristic(Operation op) {
        if (op.fullUuid == null) {
            return findCharacteristic(op.shortUuid);
        }
        for (BluetoothGattService service : gatt.getServices()) {
            BluetoothGattCharacteristic ch = service.getCharacteristic(op.fullUuid);
            if (ch != null) {
                return ch;
            }
        }
        return null;
    }

    private UUID operationUuid(Operation op) {
        return op.fullUuid == null ? uuid16(op.shortUuid) : op.fullUuid;
    }

    private boolean operationMatchesCharacteristic(Operation op, BluetoothGattCharacteristic ch) {
        if (op.fullUuid != null) {
            return op.fullUuid.equals(ch.getUuid());
        }
        return op.shortUuid == shortUuidFromUuid(ch.getUuid());
    }

    private UUID uuid16(int value) {
        return UUID.fromString(String.format(Locale.US, "0000%04x-0000-1000-8000-00805f9b34fb", value & 0xffff));
    }

    private int shortUuidFromUuid(UUID uuid) {
        if (uuid == null) {
            return -1;
        }
        String text = uuid.toString();
        if (text.startsWith("0000") && text.length() >= 8) {
            try {
                return Integer.parseInt(text.substring(4, 8), 16);
            } catch (NumberFormatException ignored) {
            }
        }
        return -1;
    }

    private void onRead(BluetoothGattCharacteristic ch, int status) {
        Operation op = current;
        if (op == null) {
            log("late read " + ch.getUuid() + " status=" + status);
            return;
        }
        byte[] value = ch.getValue();
        log("readResult " + op.name + " status=" + status + " len=" + (value == null ? 0 : value.length) + " hex=" + hex(value, 96));
        if (status == BluetoothGatt.GATT_SUCCESS && isFragmentRead(op) && value != null && handleFragmentRead(op, ch, value)) {
            return;
        }
        if (status == BluetoothGatt.GATT_SUCCESS && isLongRead(op) && value != null && handleLongRead(op, ch, value)) {
            return;
        }
        if (value != null && value.length > 0) {
            logDecoded(op, value);
        }
        current = null;
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                startNextOperation();
            }
        }, 350);
    }

    private boolean isLongRead(Operation op) {
        return op != null && (op.shortUuid == 0xd101 || op.shortUuid == 0xd103 || op.shortUuid == 0xd307
                || op.shortUuid == 0xd402 || op.shortUuid == 0xd951 || op.shortUuid == 0xda03
                || op.shortUuid == 0xd509 || op.shortUuid == 0xd805);
    }

    private boolean isFragmentRead(Operation op) {
        return op != null && op.shortUuid == 0xd003;
    }

    private boolean handleFragmentRead(final Operation op, final BluetoothGattCharacteristic ch, byte[] value) {
        if (!op.longReadStarted) {
            op.longReadStarted = true;
            op.longReadExpected = -1;
            op.longReadBuffer = new ByteArrayOutputStream();
            op.longReadIdenticalChunks = 0;
            log("  fragmentRead start");
        } else if (op.longReadLastChunk != null && Arrays.equals(op.longReadLastChunk, value)) {
            op.longReadIdenticalChunks++;
            log("  fragmentRead repeated identical chunk count=" + op.longReadIdenticalChunks);
            if (op.longReadIdenticalChunks >= 2) {
                finishLongRead(op);
                return true;
            }
        } else {
            op.longReadIdenticalChunks = 0;
        }

        op.longReadLastChunk = Arrays.copyOf(value, value.length);
        if (value.length > 0 && op.longReadBuffer.size() < maxLongReadBytes(op)) {
            int remaining = maxLongReadBytes(op) - op.longReadBuffer.size();
            op.longReadBuffer.write(value, 0, Math.min(value.length, remaining));
        }
        String collected = printable(op.longReadBuffer.toByteArray()).trim();
        log("  fragmentRead chunk len=" + value.length + " collected=" + op.longReadBuffer.size());
        if (value.length == 0 || value.length < 22 || collected.endsWith("}") || op.longReadAttempts >= 128
                || op.longReadBuffer.size() >= maxLongReadBytes(op)) {
            finishLongRead(op);
            return true;
        }
        op.longReadAttempts++;
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (current != op || gatt == null) {
                    return;
                }
                boolean ok = gatt.readCharacteristic(ch);
                log("  fragmentRead continue attempt=" + op.longReadAttempts + " ok=" + ok);
                if (!ok) {
                    finishLongRead(op);
                }
            }
        }, 150);
        return true;
    }

    private boolean handleLongRead(final Operation op, final BluetoothGattCharacteristic ch, byte[] value) {
        if (!op.longReadStarted) {
            if (value.length < 4) {
                return false;
            }
            int total = littleEndianInt(value);
            if (total <= 0 || total > maxLongReadBytes(op)) {
                log("  longRead ignored unreasonable total=" + total);
                return false;
            }
            op.longReadStarted = true;
            op.longReadExpected = total;
            op.longReadBuffer = new ByteArrayOutputStream(total);
            op.longReadLastChunk = Arrays.copyOf(value, value.length);
            writeLongChunk(op, value, 4);
            log("  longRead start total=" + total + " firstPayload=" + Math.max(0, value.length - 4) + " collected=" + op.longReadBuffer.size());
        } else {
            if (op.longReadLastChunk != null && Arrays.equals(op.longReadLastChunk, value)) {
                op.longReadIdenticalChunks++;
                log("  longRead repeated identical chunk count=" + op.longReadIdenticalChunks);
                if (op.longReadIdenticalChunks >= 2) {
                    log("  longRead aborting after repeated identical chunks");
                    finishLongRead(op);
                    return true;
                }
            } else {
                op.longReadIdenticalChunks = 0;
            }
            op.longReadLastChunk = Arrays.copyOf(value, value.length);
            writeLongChunk(op, value, 0);
            log("  longRead chunk len=" + value.length + " collected=" + op.longReadBuffer.size() + "/" + op.longReadExpected);
        }

        if (op.longReadBuffer.size() >= op.longReadExpected) {
            finishLongRead(op);
            return true;
        }
        if (op.longReadAttempts >= maxLongReadAttempts(op)) {
            log("  longRead aborting after attempts=" + op.longReadAttempts + " collected=" + op.longReadBuffer.size() + "/" + op.longReadExpected);
            finishLongRead(op);
            return true;
        }
        op.longReadAttempts++;
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (current != op || gatt == null) {
                    return;
                }
                boolean ok = gatt.readCharacteristic(ch);
                log("  longRead continue attempt=" + op.longReadAttempts + " ok=" + ok);
                if (!ok) {
                    finishLongRead(op);
                }
            }
        }, 150);
        return true;
    }

    private int maxLongReadBytes(Operation op) {
        if (op != null && (op.shortUuid == 0xd402 || op.shortUuid == 0xd951 || op.shortUuid == 0xda03)) {
            return 8 * 1024 * 1024;
        }
        if (op != null && (op.shortUuid == 0xd307 || op.shortUuid == 0xd509 || op.shortUuid == 0xd805)) {
            return 256 * 1024;
        }
        if (op != null && op.shortUuid == 0xd003) {
            return 4096;
        }
        return 5000;
    }

    private int maxLongReadAttempts(Operation op) {
        if (op == null || (op.shortUuid != 0xd402 && op.shortUuid != 0xd951 && op.shortUuid != 0xda03)
                || op.longReadExpected <= 0) {
            return 512;
        }
        return Math.max(512, (op.longReadExpected / 20) + 200);
    }

    private void writeLongChunk(Operation op, byte[] value, int offset) {
        if (op.longReadBuffer == null || value == null || offset >= value.length) {
            return;
        }
        int remaining = op.longReadExpected - op.longReadBuffer.size();
        if (remaining <= 0) {
            return;
        }
        int count = Math.min(remaining, value.length - offset);
        op.longReadBuffer.write(value, offset, count);
    }

    private void finishLongRead(Operation op) {
        byte[] payload = op.longReadBuffer == null ? new byte[0] : op.longReadBuffer.toByteArray();
        log("longResult " + op.name + " expected=" + op.longReadExpected + " actual=" + payload.length + " hex=" + hex(payload, 160));
        savePayload(op.name, payload);
        if (payload.length <= 4096) {
            log("  b64=" + android.util.Base64.encodeToString(payload, android.util.Base64.NO_WRAP));
        } else {
            log("  b64 omitted len=" + payload.length);
        }
        logLongDecoded(op, payload);
        current = null;
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                startNextOperation();
            }
        }, 350);
    }

    private void savePayload(String name, byte[] payload) {
        try {
            File dir = getExternalFilesDir(null);
            if (dir == null) {
                dir = getFilesDir();
            }
            String stamp = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date());
            File out = new File(dir, stamp + "_" + safeFileName(name) + ".bin");
            FileOutputStream fos = new FileOutputStream(out);
            try {
                fos.write(payload);
            } finally {
                fos.close();
            }
            log("  saved=" + out.getAbsolutePath());
        } catch (Throwable t) {
            log("  save failed: " + t.getClass().getSimpleName() + ": " + t.getMessage());
        }
    }

    private String safeFileName(String value) {
        if (value == null || value.length() == 0) {
            return "payload";
        }
        return value.replaceAll("[^A-Za-z0-9._-]", "_");
    }

    private void logLongDecoded(Operation op, byte[] payload) {
        String text = printable(payload);
        if (text.length() > 0) {
            log("  longText=" + redactSensitive(text));
        }
        logZipPayload(payload);
        if (op.tryDecrypt) {
            try {
                byte[] dec = aesDecrypt(payload);
                log("  longAesText=" + redactSensitive(printable(dec)));
                log("  longAesHex=" + hex(dec, 160));
                logZipPayload(dec);
            } catch (Throwable t) {
                log("  longAesDecrypt failed: " + t.getClass().getSimpleName() + ": " + t.getMessage());
            }
        }
    }

    private void logZipPayload(byte[] data) {
        if (data == null || data.length < 4 || data[0] != 0x50 || data[1] != 0x4b) {
            return;
        }
        try {
            ZipInputStream zin = new ZipInputStream(new ByteArrayInputStream(data));
            ZipEntry entry;
            byte[] buf = new byte[512];
            while ((entry = zin.getNextEntry()) != null) {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                int n;
                while ((n = zin.read(buf)) != -1) {
                    out.write(buf, 0, n);
                }
                byte[] entryBytes = out.toByteArray();
                log("  zipEntry=" + entry.getName() + " len=" + entryBytes.length + " text=" + redactSensitive(printable(entryBytes)));
                if (entryBytes.length <= 4096) {
                    log("  zipEntryB64=" + android.util.Base64.encodeToString(entryBytes, android.util.Base64.NO_WRAP));
                } else {
                    log("  zipEntryB64 omitted len=" + entryBytes.length);
                }
                zin.closeEntry();
            }
            zin.close();
        } catch (Throwable t) {
            log("  zipDecode failed: " + t.getClass().getSimpleName() + ": " + t.getMessage());
        }
    }

    private void onWrite(BluetoothGattCharacteristic ch, int status) {
        Operation op = current;
        String name = op == null ? ch.getUuid().toString() : op.name;
        log("writeResult " + name + " status=" + status);
        if (status == 3) {
            log("write status 3 treated as firmware/protocol rejection");
        }
        current = null;
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                startNextOperation();
            }
        }, operationGapMillis);
    }

    private void logDecoded(Operation op, byte[] value) {
        String rawString = printable(value);
        if (rawString.length() > 0) {
            log("  rawText=" + redactSensitive(rawString));
        }
        if (op.shortUuid == 0xd904 && value.length > 0) {
            log("  boolish=" + (value[0] & 0xff));
        }
        if (op.shortUuid == 0xd203 && value.length >= 4) {
            log("  batteryLevel=" + littleEndianInt(value));
        }
        if (op.shortUuid == 0xd204 && value.length >= 4) {
            log("  isPlugged=" + (littleEndianInt(value) == 1));
        }
        if (op.shortUuid == 0xd208 && value.length > 0) {
            int bits = value[0] & 0xff;
            log("  errorBits=0x" + String.format(Locale.US, "%02x", bits)
                    + " wifi=" + ((bits & 0x01) != 0)
                    + " bluetooth=" + ((bits & 0x02) != 0)
                    + " audio=" + ((bits & 0x04) != 0)
                    + " accelero=" + ((bits & 0x08) != 0)
                    + " pulse=" + ((bits & 0x10) != 0)
                    + " ads=" + ((bits & 0x20) != 0)
                    + " touchpad=" + ((bits & 0x40) != 0));
        }
        if (op.shortUuid == 0xd304 && value.length >= 4) {
            log("  recordStatusLE=" + littleEndianInt(value));
        }
        if ((op.shortUuid == 0xd305 || op.shortUuid == 0xd306) && value.length >= 4) {
            log("  floatLE=" + littleEndianFloat(value));
        }
        if (op.shortUuid == 0xd308 && value.length >= 4) {
            int status = littleEndianInt(value);
            log("  nightConfStatusLE=" + status
                    + " exercise=" + !containsInt(new int[] {2, 3, 6, 7, 10, 11, 14}, status)
                    + " background=" + !containsInt(new int[] {1, 3, 5, 7, 9, 11, 13, 14}, status)
                    + " alarm=" + !containsInt(new int[] {4, 5, 7, 12, 13, 14}, status)
                    + " randomObjects=" + !containsInt(new int[] {8, 9, 10, 11, 12, 13, 14}, status));
        }
        if ((op.shortUuid == 0xd309 || op.shortUuid == 0xd401 || op.shortUuid == 0xd952) && value.length > 0) {
            log("  uuid=" + uuidFromBytes(value));
        }
        if (op.shortUuid == 0xd102 && value.length > 0) {
            log("  wifiStatusLE=" + littleEndianInt(value));
        }
        if ((op.shortUuid == 0xd701 || op.shortUuid == 0xd705) && value.length >= 12) {
            log("  versionLE=" + littleEndianIntAt(value, 0) + "." + littleEndianIntAt(value, 4) + "." + littleEndianIntAt(value, 8));
        }
        if (op.shortUuid == 0xd702 && value.length > 0) {
            int offset = value.length >= 16 ? 12 : 0;
            log("  appCompatibilityLE=" + littleEndianIntAt(value, offset) + " offset=" + offset);
        }
        if ((op.shortUuid == 0xd101 || op.shortUuid == 0xd103) && value.length >= 4) {
            int total = littleEndianInt(value);
            if (total > value.length - 4) {
                log("  longValuePrefix total=" + total + " firstChunk=" + (value.length - 4));
            }
        }
        if (op.tryDecrypt) {
            try {
                byte[] dec = aesDecrypt(value);
                log("  aesText=" + redactSensitive(printable(dec)));
                log("  aesHex=" + hex(dec, 160));
            } catch (Throwable t) {
                log("  aesDecrypt failed: " + t.getClass().getSimpleName() + ": " + t.getMessage());
            }
        }
    }

    private String serverJson() {
        if ("auth-first".equals(serverJsonOrder) || "auth_api".equals(serverJsonOrder) || "auth-api".equals(serverJsonOrder)) {
            return "{\"user_auth_url\":\"" + json(authUrl) + "\",\"user_api_url\":\"" + json(apiUrl) + "\"}";
        }
        return "{\"user_api_url\":\"" + json(apiUrl) + "\",\"user_auth_url\":\"" + json(authUrl) + "\"}";
    }

    private String wifiJson() {
        return "{\"hidden\":0,\"known\":0,\"password\":\"" + json(wifiPassword) + "\",\"security\":" + wifiSecurity + ",\"SSID\":\"" + json(ssid) + "\",\"strength\":0}";
    }

    private String defaultNapConfJson() {
        int now = (int) (System.currentTimeMillis() / 1000L);
        String onset = "{\"name\":\"\",\"enabled\":0,\"id\":0,\"random_objects\":0,\"duration\":0,\"volume\":67,\"ftu\":0}";
        return "{\"sip\":{\"background\":" + onset + ",\"exercise\":" + onset + "},\"stimulations\":{\"enabled\":0},\"alarm\":{\"enabled\":0,\"id\":0,\"time\":" + now + ",\"timezone\":\"" + json(timezone) + "\",\"volume\":70,\"mode\":1,\"window\":900,\"nap_sleeping_duration\":1800}}";
    }

    private byte[] wifiPayload() {
        if ("framed".equals(wifiPayloadFormat) || "length-prefixed".equals(wifiPayloadFormat) || "length_prefixed".equals(wifiPayloadFormat)) {
            return lengthPrefixed(wifiJson());
        }
        return utf8(wifiJson());
    }

    private byte[] timePayload() {
        byte[] tz = utf8(timezone);
        ByteBuffer bb = ByteBuffer.allocate(4 + tz.length).order(ByteOrder.LITTLE_ENDIAN);
        bb.putInt((int) (System.currentTimeMillis() / 1000L));
        bb.put(tz);
        return bb.array();
    }

    private byte[] firmwareUpdatePayload(int value) {
        ByteBuffer bb = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN);
        bb.putInt(value);
        bb.putInt(2);
        return bb.array();
    }

    private byte[] intPayload(int value) {
        ByteBuffer bb = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN);
        bb.putInt(value);
        return bb.array();
    }

    private byte[] booleanPayload(boolean value) {
        return intPayload(value ? 1 : 0);
    }

    private String recordCommandName(int value) {
        switch (value) {
            case 0:
                return "recordCommand0(unknown)";
            case 1:
                return "startNight(1)";
            case 2:
                return "stopNightOrNap(2)";
            case 3:
                return "startNap(3)";
            default:
                return "none(" + value + ")";
        }
    }

    private static int littleEndianInt(byte[] value) {
        return littleEndianIntAt(value, 0);
    }

    private static int littleEndianIntAt(byte[] value, int offset) {
        int result = 0;
        if (offset < 0 || offset >= value.length) {
            return 0;
        }
        int count = Math.min(4, value.length - offset);
        for (int i = 0; i < count; i++) {
            result |= (value[offset + i] & 0xff) << (8 * i);
        }
        return result;
    }

    private static float littleEndianFloat(byte[] value) {
        return ByteBuffer.wrap(value).order(ByteOrder.LITTLE_ENDIAN).getFloat();
    }

    private static float littleEndianFloatAt(byte[] value, int offset) {
        return ByteBuffer.wrap(value, offset, 4).order(ByteOrder.LITTLE_ENDIAN).getFloat();
    }

    private static String decodeLiveEeg(byte[] value) {
        if (value == null || value.length < 16) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        sb.append(" floats0=");
        appendFourFloats(sb, value, 0);
        if (value.length >= 23) {
            sb.append(" floats7=");
            appendFourFloats(sb, value, 7);
        }
        return sb.toString();
    }

    private static void appendFourFloats(StringBuilder sb, byte[] value, int offset) {
        sb.append('[');
        for (int i = 0; i < 4; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(String.format(Locale.US, "%.6f", littleEndianFloatAt(value, offset + (4 * i))));
        }
        sb.append(']');
    }

    private static boolean containsInt(int[] values, int needle) {
        for (int value : values) {
            if (value == needle) {
                return true;
            }
        }
        return false;
    }

    private static String uuidFromBytes(byte[] value) {
        if (value == null || value.length == 0 || value.length == 1) {
            return "00000000-0000-0000-0000-000000000000";
        }
        if (value.length < 16) {
            return "invalid-len-" + value.length;
        }
        ByteBuffer bb = ByteBuffer.wrap(value);
        return new UUID(bb.getLong(), bb.getLong()).toString();
    }

    private static byte[] lengthPrefixed(String json) {
        byte[] body = utf8(json);
        ByteBuffer bb = ByteBuffer.allocate(4 + body.length).order(ByteOrder.LITTLE_ENDIAN);
        bb.putInt(body.length);
        bb.put(body);
        return bb.array();
    }

    private static byte[] aesEncrypt(byte[] plain) {
        try {
            Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(AES_KEY, "AES"), new IvParameterSpec(AES_IV));
            return cipher.doFinal(plain);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private static byte[] aesDecrypt(byte[] encrypted) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(AES_KEY, "AES"), new IvParameterSpec(AES_IV));
        return cipher.doFinal(encrypted);
    }

    private static byte[] ascii(String value) {
        try {
            return value.getBytes("US-ASCII");
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private static byte[] utf8(String value) {
        try {
            return value.getBytes("UTF-8");
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private static String printable(byte[] data) {
        if (data == null || data.length == 0) {
            return "";
        }
        try {
            String s = new String(data, "UTF-8");
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                if (c >= 32 && c < 127) {
                    out.append(c);
                } else if (c == '\n' || c == '\r' || c == '\t') {
                    out.append(c);
                } else {
                    out.append('.');
                }
            }
            return out.toString();
        } catch (Exception e) {
            return "";
        }
    }

    private static String redactSensitive(String value) {
        return value.replaceAll("(?i)(\"password\"\\s*:\\s*\")[^\"]*", "$1********");
    }

    private static String hex(byte[] data, int limit) {
        if (data == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        int n = Math.min(data.length, limit);
        for (int i = 0; i < n; i++) {
            if (i > 0) {
                sb.append(' ');
            }
            sb.append(String.format(Locale.US, "%02x", data[i] & 0xff));
        }
        if (data.length > n) {
            sb.append(" ...");
        }
        return sb.toString();
    }

    private static String characteristicProperties(BluetoothGattCharacteristic ch) {
        int props = ch.getProperties();
        StringBuilder sb = new StringBuilder();
        appendProp(sb, props, BluetoothGattCharacteristic.PROPERTY_READ, "READ");
        appendProp(sb, props, BluetoothGattCharacteristic.PROPERTY_WRITE, "WRITE");
        appendProp(sb, props, BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE, "WRITE_NR");
        appendProp(sb, props, BluetoothGattCharacteristic.PROPERTY_NOTIFY, "NOTIFY");
        appendProp(sb, props, BluetoothGattCharacteristic.PROPERTY_INDICATE, "INDICATE");
        if (sb.length() == 0) {
            sb.append("0x").append(Integer.toHexString(props));
        }
        return sb.toString();
    }

    private static void appendProp(StringBuilder sb, int props, int mask, String name) {
        if ((props & mask) == 0) {
            return;
        }
        if (sb.length() > 0) {
            sb.append('|');
        }
        sb.append(name);
    }

    private static String json(String value) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == '\\' || c == '"') {
                sb.append('\\').append(c);
            } else if (c == '\n') {
                sb.append("\\n");
            } else if (c == '\r') {
                sb.append("\\r");
            } else if (c == '\t') {
                sb.append("\\t");
            } else {
                sb.append(c);
            }
        }
        return sb.toString();
    }

    private void log(final String message) {
        String ts = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        final String line = ts + " " + message;
        android.util.Log.i(TAG, line);
        if (textView != null) {
            if (Looper.myLooper() == Looper.getMainLooper()) {
                textView.append(line + "\n");
            } else {
                handler.post(new Runnable() {
                    @Override
                    public void run() {
                        if (textView != null) {
                            textView.append(line + "\n");
                        }
                    }
                });
            }
        }
        if (logFile != null) {
            try {
                OutputStreamWriter writer = new OutputStreamWriter(new FileOutputStream(logFile, true), "UTF-8");
                writer.write(line);
                writer.write("\n");
                writer.close();
            } catch (Exception ignored) {
            }
        }
    }

    private final class GattCallbacks extends BluetoothGattCallback {
        @Override
        public void onConnectionStateChange(BluetoothGatt bluetoothGatt, int status, int newState) {
            log("connection state status=" + status + " newState=" + newState);
            if (status == BluetoothGatt.GATT_SUCCESS && newState == BluetoothGatt.STATE_CONNECTED) {
                stopScan();
                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        discover();
                    }
                }, 700);
            } else if (newState == BluetoothGatt.STATE_DISCONNECTED) {
                if (finished) {
                    log("disconnected after completion; no retry");
                } else {
                    retryConnectPreservingQueue("disconnect status=" + status);
                }
            } else if (status != BluetoothGatt.GATT_SUCCESS) {
                if (finished) {
                    log("gatt status after completion; no retry");
                } else {
                    retryConnectPreservingQueue("gatt status=" + status);
                }
            }
        }

        @Override
        public void onMtuChanged(BluetoothGatt bluetoothGatt, int mtu, int status) {
            log("mtu status=" + status + " mtu=" + mtu);
            handler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    requestDiscoverServices("mtu callback delayed");
                }
            }, 300);
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt bluetoothGatt, int status) {
            log("services discovered status=" + status);
            if (servicesReady) {
                log("services already handled; ignoring duplicate callback");
                return;
            }
            if (status != BluetoothGatt.GATT_SUCCESS) {
                serviceDiscoveryRequested = false;
                retryConnectPreservingQueue("service discovery status=" + status);
                return;
            }
            List<BluetoothGattService> discoveredServices = bluetoothGatt.getServices();
            if (discoveredServices == null || discoveredServices.isEmpty()) {
                serviceDiscoveryRequested = false;
                log("service discovery returned empty service list; retrying");
                retryConnectPreservingQueue("empty service list");
                return;
            }
            servicesReady = true;
            reconnecting = false;
            dumpServices();
            if (preserveQueueOnReconnect) {
                preserveQueueOnReconnect = false;
                log("preserving operation queue after reconnect size=" + queue.size());
                if (queue.isEmpty() && current == null) {
                    log("preserved queue is empty; rebuilding operations after reconnect");
                    buildOperations();
                }
            } else {
                buildOperations();
            }
            startNextOperation();
        }

        @Override
        public void onCharacteristicRead(BluetoothGatt bluetoothGatt, BluetoothGattCharacteristic characteristic, int status) {
            onRead(characteristic, status);
        }

        @Override
        public void onCharacteristicWrite(BluetoothGatt bluetoothGatt, BluetoothGattCharacteristic characteristic, int status) {
            onWrite(characteristic, status);
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt bluetoothGatt, BluetoothGattCharacteristic characteristic) {
            onNotify(characteristic);
        }

        @Override
        public void onDescriptorWrite(BluetoothGatt bluetoothGatt, BluetoothGattDescriptor descriptor, int status) {
            Operation op = current;
            log("descriptorWriteResult " + (op == null ? descriptor.getUuid().toString() : op.name) + " status=" + status);
            if (op != null && op.kind == Operation.KIND_SUBSCRIBE) {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    log("subscribeResult " + op.name + " status=0");
                } else {
                    log("subscribeResult " + op.name + " status=" + status);
                }
                current = null;
                startNextOperation();
            } else if (op != null && op.kind == Operation.KIND_NOTIFY) {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    beginNotifyCapture(op);
                } else {
                    finishNotifyOperation(op);
                }
            }
        }
    }

    private static final class Operation {
        static final int KIND_READ = 1;
        static final int KIND_WRITE = 2;
        static final int KIND_DELAY = 3;
        static final int KIND_NOTIFY = 4;
        static final int KIND_SUBSCRIBE = 5;

        final int kind;
        final int shortUuid;
        final UUID fullUuid;
        final String name;
        final byte[] payload;
        final boolean tryDecrypt;
        final long delayMillis;
        boolean longReadStarted;
        int longReadExpected = -1;
        int longReadAttempts;
        int longReadIdenticalChunks;
        int authRecoveries;
        boolean notifyCaptureStarted;
        byte[] longReadLastChunk;
        ByteArrayOutputStream longReadBuffer;

        private Operation(int kind, int shortUuid, UUID fullUuid, String name, byte[] payload, boolean tryDecrypt, long delayMillis) {
            this.kind = kind;
            this.shortUuid = shortUuid;
            this.fullUuid = fullUuid;
            this.name = name;
            this.payload = payload;
            this.tryDecrypt = tryDecrypt;
            this.delayMillis = delayMillis;
        }

        static Operation read(int shortUuid, String name, boolean tryDecrypt) {
            return new Operation(KIND_READ, shortUuid, null, name, null, tryDecrypt, 0);
        }

        static Operation readUuid(UUID uuid, String name, boolean tryDecrypt) {
            return new Operation(KIND_READ, -1, uuid, name, null, tryDecrypt, 0);
        }

        static Operation write(int shortUuid, String name, byte[] payload) {
            return new Operation(KIND_WRITE, shortUuid, null, name, payload, false, 0);
        }

        static Operation writeUuid(UUID uuid, String name, byte[] payload) {
            return new Operation(KIND_WRITE, -1, uuid, name, payload, false, 0);
        }

        static Operation delay(String name, long millis) {
            return new Operation(KIND_DELAY, 0, null, name, null, false, millis);
        }

        static Operation notify(int shortUuid, String name, long millis) {
            return new Operation(KIND_NOTIFY, shortUuid, null, name, null, false, millis);
        }

        static Operation notifyUuid(UUID uuid, String name, long millis) {
            return new Operation(KIND_NOTIFY, -1, uuid, name, null, false, millis);
        }

        static Operation subscribeUuid(UUID uuid, String name) {
            return new Operation(KIND_SUBSCRIBE, -1, uuid, name, null, false, 0);
        }

        void resetForRetry() {
            longReadStarted = false;
            longReadExpected = -1;
            longReadAttempts = 0;
            longReadIdenticalChunks = 0;
            authRecoveries = 0;
            notifyCaptureStarted = false;
            longReadLastChunk = null;
            longReadBuffer = null;
        }
    }
}
