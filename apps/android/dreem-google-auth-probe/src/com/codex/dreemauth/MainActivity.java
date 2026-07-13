package com.codex.dreemauth;

import android.Manifest;
import android.accounts.Account;
import android.accounts.AccountManager;
import android.accounts.AccountManagerCallback;
import android.accounts.AccountManagerFuture;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.JsonWriter;
import android.view.Gravity;
import android.widget.TextView;

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

public class MainActivity extends Activity {
    private static final int REQ_ACCOUNTS = 10;
    private static final int REQ_AUTH_INTENT = 11;
    private static final String GOOGLE_ACCOUNT_TYPE = "com.google";
    private static final String AUTH_TOKEN_TYPE = "oauth2:profile email";

    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView textView;
    private File runDir;
    private Account[] accounts = new Account[0];
    private int accountIndex = 0;
    private boolean waitingForAuthIntent = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        textView = new TextView(this);
        textView.setGravity(Gravity.START);
        textView.setTextSize(13);
        setContentView(textView);
        runDir = new File(getFilesDir(), "probe-" + System.currentTimeMillis());
        runDir.mkdirs();
        log("runDir=" + runDir.getAbsolutePath());
        if (Build.VERSION.SDK_INT >= 23 && checkSelfPermission(Manifest.permission.GET_ACCOUNTS) != PackageManager.PERMISSION_GRANTED) {
            log("requesting GET_ACCOUNTS");
            requestPermissions(new String[] { Manifest.permission.GET_ACCOUNTS }, REQ_ACCOUNTS);
        } else {
            startProbe();
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQ_ACCOUNTS) {
            boolean granted = grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED;
            log("GET_ACCOUNTS granted=" + granted);
            startProbe();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_AUTH_INTENT) {
            log("auth intent result=" + resultCode);
            waitingForAuthIntent = false;
            handler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    requestTokenForCurrentAccount();
                }
            }, 750);
        }
    }

    private void startProbe() {
        AccountManager accountManager = AccountManager.get(this);
        accounts = accountManager.getAccountsByType(GOOGLE_ACCOUNT_TYPE);
        writeAccountsSummary(accounts);
        log("google_account_count=" + accounts.length);
        if (accounts.length == 0) {
            writeFinalSummary(false, "no_google_accounts");
            return;
        }
        accountIndex = 0;
        requestTokenForCurrentAccount();
    }

    private void requestTokenForCurrentAccount() {
        if (waitingForAuthIntent) {
            return;
        }
        if (accountIndex >= accounts.length) {
            writeFinalSummary(false, "exhausted_google_accounts");
            return;
        }
        final Account account = accounts[accountIndex];
        log("requesting token for account_index=" + accountIndex + " account_sha16=" + sha16(account.name));
        AccountManager.get(this).getAuthToken(account, AUTH_TOKEN_TYPE, null, this, new AccountManagerCallback<Bundle>() {
            @Override
            public void run(AccountManagerFuture<Bundle> future) {
                try {
                    Bundle bundle = future.getResult();
                    Intent intent = bundle.getParcelable(AccountManager.KEY_INTENT);
                    if (intent != null) {
                        log("account_index=" + accountIndex + " requires auth intent");
                        waitingForAuthIntent = true;
                        startActivityForResult(intent, REQ_AUTH_INTENT);
                        return;
                    }
                    String token = bundle.getString(AccountManager.KEY_AUTHTOKEN);
                    if (token == null || token.length() == 0) {
                        log("account_index=" + accountIndex + " empty google token");
                        accountIndex++;
                        requestTokenForCurrentAccount();
                        return;
                    }
                    savePrivate("google_token_" + accountIndex + ".secret", token);
                    log("account_index=" + accountIndex + " google_token_len=" + token.length() + " google_token_sha16=" + sha16(token));
                    exchangeWithRythm(accountIndex, token);
                } catch (Exception e) {
                    log("account_index=" + accountIndex + " token_error=" + e.getClass().getSimpleName() + ":" + safeMessage(e));
                    accountIndex++;
                    requestTokenForCurrentAccount();
                }
            }
        }, handler);
    }

    private void exchangeWithRythm(final int index, final String googleToken) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                ExchangeResult result = postGoogleToken(googleToken);
                savePrivate("rythm_response_" + index + ".json", result.body);
                writeExchangeSummary(index, result);
                if (result.status == 201) {
                    try {
                        JSONObject obj = new JSONObject(result.body);
                        if (obj.has("token")) {
                            savePrivate("rythm_token_" + index + ".secret", obj.getString("token"));
                        }
                        writeFinalSummary(true, "rythm_status_201");
                        return;
                    } catch (Exception e) {
                        log("rythm parse error=" + e.getClass().getSimpleName() + ":" + safeMessage(e));
                    }
                }
                accountIndex++;
                handler.post(new Runnable() {
                    @Override
                    public void run() {
                        requestTokenForCurrentAccount();
                    }
                });
            }
        }).start();
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
            result.body = "{\"error\":\"" + e.getClass().getSimpleName() + ":" + jsonEscape(safeMessage(e)) + "\"}";
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
        return result;
    }

    private void writeAccountsSummary(Account[] accts) {
        try {
            JsonWriter writer = new JsonWriter(new FileWriter(new File(runDir, "accounts_summary.json")));
            writer.setIndent("  ");
            writer.beginObject();
            writer.name("count").value(accts.length);
            writer.name("accounts").beginArray();
            for (int i = 0; i < accts.length; i++) {
                writer.beginObject();
                writer.name("index").value(i);
                writer.name("type").value(accts[i].type);
                writer.name("name_sha16").value(sha16(accts[i].name));
                writer.endObject();
            }
            writer.endArray();
            writer.endObject();
            writer.close();
        } catch (Exception e) {
            log("accounts_summary_error=" + e.getClass().getSimpleName());
        }
    }

    private void writeExchangeSummary(int index, ExchangeResult result) {
        try {
            JSONObject body = new JSONObject(result.body);
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
            log("rythm index=" + index + " status=" + result.status + " keys=" + keys + " has_token=" + body.has("token"));
        } catch (Exception e) {
            log("exchange_summary_error=" + e.getClass().getSimpleName() + ":" + safeMessage(e));
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
            log("final_summary_error=" + e.getClass().getSimpleName());
        }
        log("final success=" + success + " reason=" + reason);
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
            log("save_error=" + name + ":" + e.getClass().getSimpleName());
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

    private void log(final String msg) {
        handler.post(new Runnable() {
            @Override
            public void run() {
                textView.append(msg + "\n");
            }
        });
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
