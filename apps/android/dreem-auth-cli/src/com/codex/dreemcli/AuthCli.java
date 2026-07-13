package com.codex.dreemcli;

import android.accounts.Account;
import android.accounts.AccountManager;
import android.content.Context;
import android.content.ContextWrapper;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.os.Looper;
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
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public class AuthCli {
    private static String targetPackage = "co.rythm.dreem2";
    private static final String GOOGLE_ACCOUNT_TYPE = "com.google";
    private static final String AUTH_TOKEN_TYPE = "oauth2:profile email";

    private final Context targetContext;
    private final File runDir;

    public static void main(String[] args) {
        int exitCode = 1;
        try {
            String command = "";
            if (args != null) {
                for (String arg : args) {
                    if (arg != null && arg.startsWith("target=")) {
                        targetPackage = arg.substring("target=".length());
                    } else if (arg != null && arg.length() > 0) {
                        command = arg;
                    }
                }
            }
            AuthCli cli = new AuthCli();
            if ("launch_signin".equals(command)) {
                exitCode = cli.launchSignInActivity();
            } else {
                exitCode = cli.run();
            }
        } catch (Throwable e) {
            System.out.println("fatal_error=" + describe(e));
        }
        System.exit(exitCode);
    }

    private AuthCli() throws Exception {
        if (Looper.myLooper() == null) {
            Looper.prepareMainLooper();
        }
        Class<?> activityThreadClass = Class.forName("android.app.ActivityThread");
        Method systemMain = activityThreadClass.getDeclaredMethod("systemMain");
        Object thread = systemMain.invoke(null);
        Method getSystemContext = activityThreadClass.getDeclaredMethod("getSystemContext");
        Context systemContext = (Context) getSystemContext.invoke(thread);
        Context appContext = createLoadedAppContext(activityThreadClass, thread, systemContext);
        if (appContext == null) {
            appContext = systemContext.createPackageContext(targetPackage, Context.CONTEXT_IGNORE_SECURITY);
        }
        targetContext = appContext;
        forceContextPackage(targetContext, targetPackage);
        runDir = new File(targetContext.getFilesDir(), "codex-auth-cli-" + System.currentTimeMillis());
        runDir.mkdirs();
    }

    private int launchSignInActivity() {
        try {
            Intent intent = new Intent();
            intent.setClassName(targetPackage, "co.rythm.dreem.ui.rework.auth.signin.SignInActivity");
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            targetContext.startActivity(intent);
            System.out.println("launch_signin_started=true");
            return 0;
        } catch (Throwable e) {
            System.out.println("launch_signin_error=" + describe(e));
            return 6;
        }
    }

    private int run() throws Exception {
        System.out.println("run_dir=" + runDir.getAbsolutePath());
        System.out.println("target_package=" + targetContext.getPackageName());
        System.out.println("op_package=" + readOpPackage(targetContext));
        System.out.println("uid=" + Process.myUid());

        Account signInAccount = getLastGoogleSignInAccount();
        if (signInAccount != null) {
            System.out.println("signin_account_sha16=" + sha16(signInAccount.name));
            if (tryTokenAndExchange("signin", signInAccount)) {
                return 0;
            }
            if (tryAccountManagerTokenAndExchange("signin", signInAccount)) {
                return 0;
            }
            writeFinalSummary(false, "signin_account_token_failed");
            return 5;
        }

        AccountManager accountManager = AccountManager.get(targetContext);
        Account[] accounts = accountManager.getAccountsByType(GOOGLE_ACCOUNT_TYPE);
        writeAccountsSummary(accounts);
        System.out.println("google_account_count=" + accounts.length);
        if (accounts.length == 0) {
            writeFinalSummary(false, "no_google_accounts_or_signin");
            return 2;
        }

        for (int i = 0; i < accounts.length; i++) {
            Account account = accounts[i];
            System.out.println("account_" + i + "_sha16=" + sha16(account.name));
            if (tryTokenAndExchange(Integer.toString(i), account)) {
                return 0;
            }
            if (tryAccountManagerTokenAndExchange(Integer.toString(i), account)) {
                return 0;
            }
        }

        writeFinalSummary(false, "exhausted_google_accounts");
        return 4;
    }

    private Account getLastGoogleSignInAccount() {
        try {
            ClassLoader loader = targetContext.getClassLoader();
            Class<?> googleSignInClass = loader.loadClass("com.google.android.gms.auth.api.signin.a");
            Method getLastSignedIn = googleSignInClass.getDeclaredMethod("a", Context.class);
            Object signInAccount = getLastSignedIn.invoke(null, googleAuthContext());
            if (signInAccount == null) {
                System.out.println("signin_account_present=false");
                return null;
            }
            Class<?> accountClass = loader.loadClass("com.google.android.gms.auth.api.signin.GoogleSignInAccount");
            Method getAccount = accountClass.getDeclaredMethod("f");
            Account account = (Account) getAccount.invoke(signInAccount);
            System.out.println("signin_account_present=true");
            if (account == null) {
                System.out.println("signin_account_error=null_android_account");
            }
            return account;
        } catch (Throwable e) {
            System.out.println("signin_account_error=" + describe(e));
            return null;
        }
    }

    private boolean tryTokenAndExchange(String id, Account account) {
        try {
            String token = getGoogleToken(account);
            if (token == null || token.length() == 0) {
                System.out.println("account_" + id + "_token_error=empty_token");
                return false;
            }
            savePrivate("google_token_" + id + ".secret", token);
            System.out.println("account_" + id + "_google_token_len=" + token.length());
            System.out.println("account_" + id + "_google_token_sha16=" + sha16(token));

            ExchangeResult exchange = postGoogleToken(token);
            savePrivate("rythm_response_" + id + ".json", exchange.body);
            writeExchangeSummary(id, exchange);
            if (exchange.status == 201) {
                JSONObject body = new JSONObject(exchange.body);
                if (body.has("token")) {
                    String rythmToken = body.getString("token");
                    savePrivate("rythm_token_" + id + ".secret", rythmToken);
                    System.out.println("account_" + id + "_rythm_token_len=" + rythmToken.length());
                    System.out.println("account_" + id + "_rythm_token_sha16=" + sha16(rythmToken));
                }
                writeFinalSummary(true, "rythm_status_201");
                return true;
            }
        } catch (Throwable e) {
            System.out.println("account_" + id + "_token_error=" + describe(e));
        }
        return false;
    }

    private String getGoogleToken(Account account) throws Exception {
        return callOffMainThread(new Callable<String>() {
            @Override
            public String call() throws Exception {
                ClassLoader loader = targetContext.getClassLoader();
                Class<?> googleAuthUtil = loader.loadClass("com.google.android.gms.auth.a");
                Method getToken = googleAuthUtil.getDeclaredMethod("a", Context.class, Account.class, String.class);
                return (String) getToken.invoke(null, googleAuthContext(), account, AUTH_TOKEN_TYPE);
            }
        });
    }

    private Context googleAuthContext() {
        return new ContextWrapper(targetContext) {
            @Override
            public Context getApplicationContext() {
                return this;
            }

            @Override
            public String getPackageName() {
                return targetPackage;
            }
        };
    }

    private <T> T callOffMainThread(Callable<T> callable) throws Exception {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            return callable.call();
        }
        FutureTask<T> task = new FutureTask<T>(callable);
        Thread thread = new Thread(task, "dreem-auth-cli-worker");
        thread.start();
        try {
            return task.get(60, TimeUnit.SECONDS);
        } catch (ExecutionException e) {
            Throwable cause = e.getCause();
            if (cause instanceof Exception) {
                throw (Exception) cause;
            }
            if (cause instanceof Error) {
                throw (Error) cause;
            }
            throw new RuntimeException(cause);
        }
    }

    private boolean tryAccountManagerTokenAndExchange(final String index, final Account accountManagerAccount) {
        try {
            android.os.Bundle result = callOffMainThread(new Callable<android.os.Bundle>() {
                @Override
                public android.os.Bundle call() throws Exception {
                    AccountManager accountManager = AccountManager.get(targetContext);
                    return accountManager.getAuthToken(accountManagerAccount, AUTH_TOKEN_TYPE, null, false, null, null)
                            .getResult(60, TimeUnit.SECONDS);
                }
            });
            Intent intent = result.getParcelable(AccountManager.KEY_INTENT);
            if (intent != null) {
                savePrivate("auth_intent_" + index + ".txt", intent.toUri(0));
                System.out.println("account_" + index + "_needs_intent=true");
                writeFinalSummary(false, "requires_auth_intent");
                return false;
            }
            String token = result.getString(AccountManager.KEY_AUTHTOKEN);
            if (token == null || token.length() == 0) {
                System.out.println("account_" + index + "_token_error=empty_token");
                return false;
            }
            savePrivate("google_token_" + index + ".secret", token);
            System.out.println("account_" + index + "_google_token_len=" + token.length());
            System.out.println("account_" + index + "_google_token_sha16=" + sha16(token));
            ExchangeResult exchange = postGoogleToken(token);
            savePrivate("rythm_response_" + index + ".json", exchange.body);
            writeExchangeSummary(index, exchange);
            if (exchange.status == 201) {
                JSONObject body = new JSONObject(exchange.body);
                if (body.has("token")) {
                    String rythmToken = body.getString("token");
                    savePrivate("rythm_token_" + index + ".secret", rythmToken);
                    System.out.println("account_" + index + "_rythm_token_len=" + rythmToken.length());
                    System.out.println("account_" + index + "_rythm_token_sha16=" + sha16(rythmToken));
                }
                writeFinalSummary(true, "rythm_status_201");
                return true;
            }
        } catch (Throwable e) {
            System.out.println("account_" + index + "_token_error=" + describe(e));
        }
        return false;
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
            System.out.println("accounts_summary_error=" + e.getClass().getSimpleName() + ":" + safeMessage(e));
        }
    }

    private void writeExchangeSummary(String index, ExchangeResult result) {
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
            System.out.println("account_" + index + "_rythm_status=" + result.status);
            System.out.println("account_" + index + "_rythm_keys=" + keys);
            System.out.println("account_" + index + "_rythm_has_token=" + body.has("token"));
        } catch (Exception e) {
            System.out.println("exchange_summary_error=" + e.getClass().getSimpleName() + ":" + safeMessage(e));
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
            System.out.println("final_summary_error=" + e.getClass().getSimpleName() + ":" + safeMessage(e));
        }
        System.out.println("final_success=" + success);
        System.out.println("final_reason=" + reason);
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
            System.out.println("save_error_" + name + "=" + e.getClass().getSimpleName() + ":" + safeMessage(e));
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

    private static String sha16(String value) {
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

    private static String safeMessage(Exception e) {
        String msg = e.getMessage();
        return msg == null ? "" : msg;
    }

    private static void forceContextPackage(Context context, String packageName) {
        setStringField(context, "mBasePackageName", packageName);
        setStringField(context, "mOpPackageName", packageName);
    }

    private static Context createLoadedAppContext(Class<?> activityThreadClass, Object thread, Context systemContext) {
        try {
            ApplicationInfo appInfo = systemContext.getPackageManager().getApplicationInfo(targetPackage, 0);
            Class<?> compatibilityInfoClass = Class.forName("android.content.res.CompatibilityInfo");
            Field defaultCompatibility = compatibilityInfoClass.getDeclaredField("DEFAULT_COMPATIBILITY_INFO");
            defaultCompatibility.setAccessible(true);
            Object compatibility = defaultCompatibility.get(null);

            Method getPackageInfoNoCheck = activityThreadClass.getDeclaredMethod(
                    "getPackageInfoNoCheck", ApplicationInfo.class, compatibilityInfoClass);
            getPackageInfoNoCheck.setAccessible(true);
            Object loadedApk = getPackageInfoNoCheck.invoke(thread, appInfo, compatibility);

            Class<?> contextImplClass = Class.forName("android.app.ContextImpl");
            Class<?> loadedApkClass = Class.forName("android.app.LoadedApk");
            Method createAppContext = contextImplClass.getDeclaredMethod(
                    "createAppContext", activityThreadClass, loadedApkClass);
            createAppContext.setAccessible(true);
            return (Context) createAppContext.invoke(null, thread, loadedApk);
        } catch (Throwable e) {
            System.out.println("create_loaded_context_error=" + describe(e));
            return null;
        }
    }

    private static void setStringField(Object target, String fieldName, String value) {
        Class<?> current = target.getClass();
        while (current != null) {
            try {
                Field field = current.getDeclaredField(fieldName);
                field.setAccessible(true);
                field.set(target, value);
                return;
            } catch (NoSuchFieldException e) {
                current = current.getSuperclass();
            } catch (Throwable e) {
                System.out.println("set_" + fieldName + "_error=" + describe(e));
                return;
            }
        }
        System.out.println("set_" + fieldName + "_error=missing_field");
    }

    private static String readOpPackage(Context context) {
        try {
            Method method = Context.class.getMethod("getOpPackageName");
            Object value = method.invoke(context);
            return value == null ? "" : value.toString();
        } catch (Throwable e) {
            return "read_error:" + describe(e);
        }
    }

    private static String describe(Throwable throwable) {
        StringBuilder builder = new StringBuilder();
        Throwable current = throwable;
        int depth = 0;
        while (current != null && depth < 4) {
            if (depth > 0) {
                builder.append(" <- ");
            }
            builder.append(current.getClass().getSimpleName()).append(":");
            String msg = current.getMessage();
            if (msg != null) {
                builder.append(msg);
            }
            current = current.getCause();
            depth++;
        }
        return builder.toString();
    }

    private static String jsonEscape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static class ExchangeResult {
        int status;
        String body = "";
    }
}
