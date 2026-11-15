package local.lastinput;

import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.AccessibilityEvent;
import android.os.SystemClock;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.media.tv.TvContract;
import android.media.tv.TvInputInfo;
import android.media.tv.TvInputManager;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Log;

import java.io.BufferedReader;
import java.io.FileWriter;
import java.io.InputStreamReader;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Remembers the last passthrough TV input (HDMI etc.) and re-tunes to it when
 * the TV boots or wakes, replacing the stock launcher's "power on to last input".
 */
public class WatchService extends AccessibilityService {
    private static final String TAG = "LastInput";
    private static final long POLL_MS = 5000;
    private static final long LAUNCH_DELAY_MS = 2500;
    private static final Pattern ID = Pattern.compile("^\\s*inputId:\\s*(\\S+)\\s*$");

    private SharedPreferences prefs;
    private HandlerThread thread;
    private Handler h;
    private boolean screenOn = true;

    private final Runnable poll = new Runnable() {
        @Override public void run() {
            try { if (screenOn) recordCurrentInput(); } catch (Throwable t) { Log.w(TAG, t); }
            h.postDelayed(this, POLL_MS);
        }
    };

    private final BroadcastReceiver screen = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent i) {
            flog("screen action " + i.getAction());
            if (Intent.ACTION_SCREEN_ON.equals(i.getAction())) {
                screenOn = true;
                scheduleLaunch();
            } else {
                screenOn = false;
            }
        }
    };

    private boolean started = false;

    @Override protected void onServiceConnected() {
        super.onServiceConnected();
        flog("connected uptime=" + SystemClock.elapsedRealtime() / 1000);
        if (started) return;
        started = true;
        prefs = getSharedPreferences("p", MODE_PRIVATE);
        thread = new HandlerThread("lastinput");
        thread.start();
        h = new Handler(thread.getLooper());
        IntentFilter f = new IntentFilter();
        f.addAction(Intent.ACTION_SCREEN_ON);
        f.addAction(Intent.ACTION_SCREEN_OFF);
        registerReceiver(screen, f);
        h.post(poll);
        // Cold boot: the system binds us right after startup, so uptime is small.
        if (SystemClock.elapsedRealtime() < 3 * 60 * 1000) scheduleLaunch();
    }

    @Override public void onAccessibilityEvent(AccessibilityEvent e) {}
    @Override public void onInterrupt() {}

    private void flog(String m) {
        Log.i(TAG, m);
        try { FileWriter w = new FileWriter(new java.io.File(getFilesDir(), "log.txt"), true);
              w.write(new java.util.Date() + " " + m + "\n"); w.close(); } catch (Throwable ignored) {}
    }

    private void scheduleLaunch() {
        flog("scheduleLaunch");
        h.postDelayed(new Runnable() { @Override public void run() { launchLast(); } }, LAUNCH_DELAY_MS);
    }

    private void launchLast() {
        String id = prefs.getString("last", null);
        if (id == null) { flog("no last input recorded"); return; }
        try {
            Intent i = new Intent(Intent.ACTION_VIEW, TvContract.buildChannelUriForPassthroughInput(id));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
            flog("launched " + id);
        } catch (Throwable t) { flog("launch failed " + t); }
    }

    private void recordCurrentInput() throws Exception {
        Process p = Runtime.getRuntime().exec(new String[]{"dumpsys", "tv_input"});
        String found = null;
        BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream()));
        String line;
        boolean inSessions = false;
        while ((line = r.readLine()) != null) {
            if (line.contains("sessionStateMap")) { inSessions = true; continue; }
            if (inSessions) {
                if (line.contains("mHardwareInputIdMap") || line.contains("callbackSet")
                        || line.contains("serviceStateMap") || line.contains("clientStateMap")) { inSessions = false; continue; }
                Matcher m = ID.matcher(line);
                if (m.matches()) found = m.group(1);
            }
        }
        r.close();
        int rc = p.waitFor();
        if (found == null) {
            BufferedReader er = new BufferedReader(new InputStreamReader(p.getErrorStream()));
            String el = er.readLine();
            Log.i(TAG, "no session; rc=" + rc + " err=" + el);
        }
        if (found == null || found.equals(prefs.getString("last", null))) return;
        TvInputManager tm = (TvInputManager) getSystemService(Context.TV_INPUT_SERVICE);
        TvInputInfo info = tm.getTvInputInfo(found);
        if (info != null && info.isPassthroughInput()) {
            prefs.edit().putString("last", found).apply();
            Log.i(TAG, "recorded " + found);
        }
    }

    @Override public void onDestroy() {
        try { unregisterReceiver(screen); } catch (Throwable ignored) {}
        thread.quitSafely();
        super.onDestroy();
    }

}
