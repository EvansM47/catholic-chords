package ke.co.catholicchoir.collaboration;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.webkit.JavascriptInterface;

import com.getcapacitor.BridgeActivity;
import com.google.mlkit.vision.barcode.common.Barcode;
import com.google.mlkit.vision.codescanner.GmsBarcodeScanner;
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions;
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Enumeration;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class MainActivity extends BridgeActivity {
    private final ChoirNativeBridge choirBridge = new ChoirNativeBridge();

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (getBridge() != null && getBridge().getWebView() != null) {
            getBridge().getWebView().addJavascriptInterface(choirBridge, "ChoirNative");
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (getBridge() != null && getBridge().getWebView() != null) {
            getBridge().getWebView().evaluateJavascript(
                "window.dispatchEvent(new Event('choirNativeBack'))", null);
            return;
        }
        super.onBackPressed();
    }

    @Override
    public void onDestroy() {
        choirBridge.stopSession();
        choirBridge.disconnectSession();
        super.onDestroy();
    }

    private final class ChoirNativeBridge {
        private final Set<SessionClient> clients = ConcurrentHashMap.newKeySet();
        private final Object memberLock = new Object();
        private volatile ServerSocket server;
        private volatile BufferedWriter memberWriter;
        private volatile Socket memberSocket;
        private volatile String leaderName = "Choir leader";
        private volatile boolean running;

        @JavascriptInterface
        public void exitApp() {
            runOnUiThread(() -> moveTaskToBack(true));
        }

        @JavascriptInterface
        public boolean copyToClipboard(String text) {
            try {
                ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (clipboard == null) return false;
                clipboard.setPrimaryClip(ClipData.newPlainText("Order of Mass", text == null ? "" : text));
                return true;
            } catch (RuntimeException error) {
                return false;
            }
        }

        @JavascriptInterface
        public boolean shareText(String title, String text) {
            try {
                runOnUiThread(() -> {
                    Intent sendIntent = new Intent(Intent.ACTION_SEND);
                    sendIntent.setType("text/plain");
                    sendIntent.putExtra(Intent.EXTRA_SUBJECT, title == null ? "Mass order" : title);
                    sendIntent.putExtra(Intent.EXTRA_TEXT, text == null ? "" : text);
                    startActivity(Intent.createChooser(sendIntent, "Share Mass order"));
                });
                return true;
            } catch (RuntimeException error) {
                return false;
            }
        }

        @JavascriptInterface
        public String startSession(String displayName) {
            try {
                if (server == null || server.isClosed()) {
                    ServerSocket socket = new ServerSocket();
                    socket.setReuseAddress(true);
                    socket.bind(new InetSocketAddress(0));
                    server = socket;
                    running = true;
                    leaderName = cleanName(displayName, "Choir leader");
                    Thread accept = new Thread(() -> acceptMembers(socket), "choir-session-host");
                    accept.setDaemon(true);
                    accept.start();
                }
                JSONObject response = new JSONObject();
                response.put("started", true);
                response.put("address", hotspotAddress());
                response.put("port", server.getLocalPort());
                response.put("leader", leaderName);
                return response.toString();
            } catch (Exception error) {
                return errorJson("startError", error.getMessage());
            }
        }

        @JavascriptInterface
        public void scanSessionInvite() {
            runOnUiThread(() -> {
                GmsBarcodeScannerOptions options = new GmsBarcodeScannerOptions.Builder()
                    .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                    .enableAutoZoom()
                    .build();
                GmsBarcodeScanner scanner = GmsBarcodeScanning.getClient(MainActivity.this, options);
                scanner.startScan()
                    .addOnSuccessListener(barcode -> {
                        JSONObject message = new JSONObject();
                        try {
                            message.put("type", "inviteScanned");
                            message.put("value", barcode.getRawValue() == null ? "" : barcode.getRawValue());
                        } catch (JSONException ignored) { }
                        emitToPage(message.toString());
                    })
                    .addOnCanceledListener(() -> emitToPage("{\"type\":\"inviteScanCanceled\"}"))
                    .addOnFailureListener(error -> emitToPage(errorJson("inviteScanError", error.getMessage())));
            });
        }

        @JavascriptInterface
        public void stopSession() {
            running = false;
            ServerSocket active = server;
            server = null;
            if (active != null) {
                try { active.close(); } catch (Exception ignored) { }
            }
            for (SessionClient client : clients) client.close();
            clients.clear();
            emitToPage("{\"type\":\"sessionStopped\"}");
        }

        @JavascriptInterface
        public void connectToSession(String address, String portText, String displayName) {
            disconnectSession();
            Thread connect = new Thread(() -> {
                try {
                    int port = Integer.parseInt(portText);
                    Socket socket = new Socket();
                    socket.connect(new InetSocketAddress(address.trim(), port), 5000);
                    memberSocket = socket;
                    BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8));
                    memberWriter = writer;
                    JSONObject join = new JSONObject();
                    join.put("type", "join");
                    join.put("name", cleanName(displayName, "Choir member"));
                    writeLine(writer, join.toString());
                    emitToPage("{\"type\":\"connecting\"}");
                    try (BufferedReader reader = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8))) {
                        String line;
                        while ((line = reader.readLine()) != null) emitToPage(line);
                    }
                } catch (Exception error) {
                    emitToPage(errorJson("connectionError", error.getMessage()));
                } finally {
                    disconnectSession();
                    emitToPage("{\"type\":\"disconnected\"}");
                }
            }, "choir-session-member");
            connect.setDaemon(true);
            connect.start();
        }

        @JavascriptInterface
        public void disconnectSession() {
            BufferedWriter writer = memberWriter;
            Socket socket = memberSocket;
            memberWriter = null;
            memberSocket = null;
            try { if (writer != null) writer.close(); } catch (Exception ignored) { }
            try { if (socket != null) socket.close(); } catch (Exception ignored) { }
        }

        @JavascriptInterface
        public void sendSessionMessage(String message) {
            BufferedWriter writer = memberWriter;
            if (writer != null) {
                try { writeLine(writer, message); } catch (Exception error) { emitToPage(errorJson("sendError", error.getMessage())); }
            }
        }

        @JavascriptInterface
        public void broadcastSessionMessage(String message) {
            for (SessionClient client : clients) client.send(message);
        }

        private void acceptMembers(ServerSocket listening) {
            while (running && !listening.isClosed()) {
                try {
                    Socket socket = listening.accept();
                    Thread worker = new Thread(() -> handleMember(socket), "choir-session-peer");
                    worker.setDaemon(true);
                    worker.start();
                } catch (Exception error) {
                    if (running) emitToPage(errorJson("serverError", error.getMessage()));
                    return;
                }
            }
        }

        private void handleMember(Socket socket) {
            SessionClient client = null;
            try {
                BufferedReader reader = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
                BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8));
                String first = reader.readLine();
                if (first == null) return;
                JSONObject join = new JSONObject(first);
                String requestedName = cleanName(join.optString("name"), "Choir member");
                synchronized (memberLock) {
                    boolean nameTaken = requestedName.equalsIgnoreCase(leaderName);
                    if (!nameTaken) {
                        for (SessionClient existing : clients) {
                            if (requestedName.equalsIgnoreCase(existing.name)) {
                                nameTaken = true;
                                break;
                            }
                        }
                    }
                    if (nameTaken) {
                        JSONObject rejected = new JSONObject();
                        rejected.put("type", "nameTaken");
                        rejected.put("message", "That display name is already in use in this session.");
                        writeLine(writer, rejected.toString());
                        return;
                    }
                    client = new SessionClient(socket, writer, requestedName);
                    clients.add(client);
                }
                JSONObject welcome = new JSONObject();
                welcome.put("type", "welcome");
                welcome.put("leader", leaderName);
                client.send(welcome.toString());
                broadcastMembers();
                String line;
                while ((line = reader.readLine()) != null) {
                    JSONObject message = new JSONObject(line);
                    String messageType = message.optString("type");
                    if ("vote".equals(messageType) || "suggestion".equals(messageType)) {
                        message.put("from", client.name);
                        emitToPage(message.toString());
                        broadcastToMembers(message.toString(), client);
                    }
                }
            } catch (Exception ignored) {
            } finally {
                if (client != null) {
                    clients.remove(client);
                    broadcastMembers();
                    client.close();
                } else {
                    try { socket.close(); } catch (Exception ignored) { }
                }
            }
        }

        private void broadcastMembers() {
            JSONArray names = new JSONArray();
            for (SessionClient client : clients) {
                JSONObject member = new JSONObject();
                try { member.put("name", client.name); } catch (JSONException ignored) { }
                names.put(member);
            }
            JSONObject update = new JSONObject();
            try {
                update.put("type", "members");
                update.put("members", names);
                update.put("leader", leaderName);
            } catch (JSONException ignored) { }
            String line = update.toString();
            emitToPage(line);
            broadcastToMembers(line, null);
        }

        private void broadcastToMembers(String line, SessionClient except) {
            for (SessionClient client : clients) if (client != except) client.send(line);
        }

        private void emitToPage(String json) {
            runOnUiThread(() -> {
                if (getBridge() == null || getBridge().getWebView() == null) return;
                String quoted = JSONObject.quote(json);
                getBridge().getWebView().evaluateJavascript(
                    "window.dispatchEvent(new CustomEvent('choirSessionMessage',{detail:" + quoted + "}))", null);
            });
        }

        private String hotspotAddress() {
            String fallback = "";
            try {
                Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
                for (NetworkInterface network : Collections.list(interfaces)) {
                    if (!network.isUp() || network.isLoopback()) continue;
                    for (InetAddress address : Collections.list(network.getInetAddresses())) {
                        if (!(address instanceof Inet4Address) || address.isLoopbackAddress() || !address.isSiteLocalAddress()) continue;
                        String value = address.getHostAddress();
                        if (value.startsWith("192.168.") && value.endsWith(".1")) return value;
                        if (fallback.isEmpty()) fallback = value;
                    }
                }
            } catch (Exception ignored) { }
            return fallback;
        }

        private String cleanName(String value, String fallback) {
            String clean = value == null ? "" : value.replaceAll("[\\r\\n]", "").trim();
            return clean.isEmpty() ? fallback : clean.substring(0, Math.min(32, clean.length()));
        }

        private String errorJson(String type, String message) {
            JSONObject error = new JSONObject();
            try {
                error.put("type", type);
                error.put("message", message == null ? "Unable to open the local Wi-Fi session." : message);
            } catch (JSONException ignored) { }
            return error.toString();
        }

        private void writeLine(BufferedWriter writer, String line) throws Exception {
            synchronized (writer) {
                writer.write(line.replace("\n", "").replace("\r", ""));
                writer.newLine();
                writer.flush();
            }
        }

        private final class SessionClient {
            final Socket socket;
            final BufferedWriter writer;
            final String name;

            SessionClient(Socket socket, BufferedWriter writer, String name) {
                this.socket = socket;
                this.writer = writer;
                this.name = name;
            }

            void send(String line) {
                try { writeLine(writer, line); } catch (Exception ignored) { close(); }
            }

            void close() {
                try { socket.close(); } catch (Exception ignored) { }
            }
        }
    }
}
