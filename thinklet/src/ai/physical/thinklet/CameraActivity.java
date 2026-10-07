package ai.physical.thinklet;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.ImageFormat;
import android.hardware.camera2.*;
import android.media.Image;
import android.media.ImageReader;
import android.os.*;
import android.util.Size;
import android.view.WindowManager;
import android.widget.TextView;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.concurrent.*;

/** Camera frames stay on the local USB/ADB link; no cloud upload. */
public class CameraActivity extends Activity {
    private HandlerThread worker;
    private Handler handler;
    private CameraDevice camera;
    private CameraCaptureSession session;
    private CaptureRequest.Builder request;
    private ImageReader reader;
    private ServerSocket server;
    private final ExecutorService clients = Executors.newFixedThreadPool(3);
    private volatile boolean active, alive = true, lockSupported, exposureLocked;
    private volatile String state = "STARTING", error = "", cameraId = "";
    private volatile long frameAt = 0, frames = 0, lastProcessed = 0;
    private volatile double brightness = 0;
    private volatile byte[] jpeg;
    private int width = 320, height = 240;
    private TextView label;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        label = new TextView(this);
        label.setTextSize(24); label.setPadding(28, 40, 28, 28);
        label.setText("Physical AI\nCamera brightness → robot arm\nUSB control board on your computer");
        setContentView(label);
        worker = new HandlerThread("CameraAnalysis"); worker.start();
        handler = new Handler(worker.getLooper());
        new Thread(this::serve, "CameraHttp").start();
    }

    @Override public void onResume() {
        super.onResume(); active = true;
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            state = "PERMISSION_REQUIRED";
            requestPermissions(new String[]{Manifest.permission.CAMERA}, 1);
        } else handler.post(this::openCamera);
    }

    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(code, permissions, grants);
        if (code == 1 && grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED && active)
            handler.post(this::openCamera);
        else state = "PERMISSION_REQUIRED";
    }

    @Override public void onPause() {
        active = false;
        handler.post(() -> { closeCamera(); state = "PAUSED"; jpeg = null; frameAt = 0; });
        super.onPause();
    }

    @Override public void onDestroy() {
        alive = false;
        try { if (server != null) server.close(); } catch (IOException ignored) {}
        clients.shutdownNow(); worker.quitSafely();
        super.onDestroy();
    }

    private void fail(String message) {
        state = "ERROR"; error = message; jpeg = null; frameAt = 0;
        runOnUiThread(() -> label.setText("Physical AI\nCamera error: " + message));
    }

    private void openCamera() {
        if (!active || camera != null) return;
        try {
            CameraManager manager = (CameraManager)getSystemService(CAMERA_SERVICE);
            String[] ids = manager.getCameraIdList();
            if (ids.length == 0) { fail("No camera found"); return; }
            cameraId = ids[0];
            CameraCharacteristics info = manager.getCameraCharacteristics(cameraId);
            lockSupported = Boolean.TRUE.equals(info.get(CameraCharacteristics.CONTROL_AE_LOCK_AVAILABLE));
            Size[] sizes = info.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
                .getOutputSizes(ImageFormat.YUV_420_888);
            Size chosen = Arrays.stream(sizes).min(Comparator.comparingLong(s ->
                Math.abs((long)s.getWidth()*s.getHeight() - 320*240))).get();
            width = chosen.getWidth(); height = chosen.getHeight();
            reader = ImageReader.newInstance(width, height, ImageFormat.YUV_420_888, 3);
            reader.setOnImageAvailableListener(this::analyze, handler);
            state = "OPENING"; error = ""; exposureLocked = false;
            manager.openCamera(cameraId, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice device) {
                    if (!active) { device.close(); return; }
                    camera = device; startSession();
                }
                @Override public void onDisconnected(CameraDevice device) {
                    device.close(); closeCamera(); fail("Camera disconnected");
                }
                @Override public void onError(CameraDevice device, int code) {
                    device.close(); closeCamera(); fail("Camera error " + code);
                }
            }, handler);
        } catch (Exception e) { closeCamera(); fail(e.toString()); }
    }

    private void startSession() {
        try {
            request = camera.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
            request.addTarget(reader.getSurface());
            request.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON);
            camera.createCaptureSession(Collections.singletonList(reader.getSurface()),
                new CameraCaptureSession.StateCallback() {
                    @Override public void onConfigured(CameraCaptureSession configured) {
                        if (!active || camera == null) { configured.close(); return; }
                        session = configured; updateExposure(false);
                        CameraCaptureSession current = configured;
                        handler.postDelayed(() -> { if (session == current) updateExposure(true); }, 2500);
                    }
                    @Override public void onConfigureFailed(CameraCaptureSession configured) {
                        configured.close(); fail("Camera session could not start");
                    }
                }, handler);
        } catch (Exception e) { fail(e.toString()); }
    }

    private void updateExposure(boolean locked) {
        if (session == null || request == null) return;
        try {
            request.set(CaptureRequest.CONTROL_AE_LOCK, locked && lockSupported);
            session.setRepeatingRequest(request.build(), new CameraCaptureSession.CaptureCallback() {
                @Override public void onCaptureCompleted(CameraCaptureSession s, CaptureRequest r, TotalCaptureResult result) {
                    exposureLocked = Boolean.TRUE.equals(result.get(CaptureResult.CONTROL_AE_LOCK));
                }
            }, handler);
        } catch (Exception e) { fail(e.toString()); }
    }

    private void resetExposure() {
        handler.post(() -> {
            updateExposure(false);
            CameraCaptureSession current = session;
            handler.postDelayed(() -> { if (current != null && session == current) updateExposure(true); }, 2500);
        });
    }

    private void analyze(ImageReader source) {
        try (Image image = source.acquireLatestImage()) {
            if (image == null || !active) return;
            long now = SystemClock.elapsedRealtime();
            if (now - lastProcessed < 180) return;
            lastProcessed = now;
            Image.Plane[] planes = image.getPlanes();
            ByteBuffer y = planes[0].getBuffer(), u = planes[1].getBuffer(), v = planes[2].getBuffer();
            int[] rgb = new int[width*height]; long sum = 0;
            for (int row = 0; row < height; row++) for (int col = 0; col < width; col++) {
                int luma = y.get(row*planes[0].getRowStride()+col*planes[0].getPixelStride()) & 255;
                int cb = (u.get((row/2)*planes[1].getRowStride()+(col/2)*planes[1].getPixelStride()) & 255)-128;
                int cr = (v.get((row/2)*planes[2].getRowStride()+(col/2)*planes[2].getPixelStride()) & 255)-128;
                sum += luma;
                int yy = Math.max(0, luma-16)*298;
                int red = clamp((yy+409*cr+128)>>8), green = clamp((yy-100*cb-208*cr+128)>>8);
                int blue = clamp((yy+516*cb+128)>>8);
                rgb[row*width+col] = 0xff000000 | red<<16 | green<<8 | blue;
            }
            Bitmap bitmap = Bitmap.createBitmap(rgb, width, height, Bitmap.Config.ARGB_8888);
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            bitmap.compress(Bitmap.CompressFormat.JPEG, 75, bytes); bitmap.recycle();
            jpeg = bytes.toByteArray(); brightness = sum*100.0/(width*height*255.0);
            frames++; frameAt = now; state = "READY"; error = "";
            if (frames % 10 == 0) runOnUiThread(() -> label.setText(String.format(Locale.US,
                "Physical AI\nCamera brightness: %.1f%%\nExposure lock: %s\nUSB board connected via ADB",
                brightness, exposureLocked ? "ON" : "OFF")));
        } catch (Exception e) { if (active) fail(e.toString()); }
    }

    private int clamp(int value) { return Math.max(0, Math.min(255, value)); }
    private void closeCamera() {
        if (session != null) { session.close(); session = null; }
        if (camera != null) { camera.close(); camera = null; }
        if (reader != null) { reader.close(); reader = null; }
        request = null; exposureLocked = false;
    }

    private byte[] status() throws Exception {
        JSONObject json = new JSONObject();
        json.put("state", state); json.put("error", error); json.put("camera_id", cameraId);
        json.put("brightness", brightness); json.put("frames", frames);
        json.put("frame_age_ms", frameAt == 0 ? -1 : SystemClock.elapsedRealtime()-frameAt);
        json.put("exposure_locked", exposureLocked); json.put("lock_supported", lockSupported);
        json.put("width", width); json.put("height", height);
        return json.toString().getBytes("UTF-8");
    }

    private void serve() {
        try {
            server = new ServerSocket(); server.setReuseAddress(true);
            server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 8765), 8);
            while (alive) { Socket socket = server.accept(); clients.execute(() -> respond(socket)); }
        } catch (Exception e) { if (alive) fail("Local server: " + e.toString()); }
    }

    private void respond(Socket socket) {
        try (Socket connection = socket) {
            connection.setSoTimeout(2000);
            BufferedReader input = new BufferedReader(new InputStreamReader(connection.getInputStream(), "UTF-8"));
            String first = input.readLine();
            if (first == null || first.length() > 4096) return;
            String[] parts = first.split(" ");
            if (parts.length < 2) return;
            String path = parts[1].split("\\?")[0];
            byte[] body; String type = "application/json"; int code = 200;
            if (parts[0].equals("GET") && path.equals("/status")) body = status();
            else if (parts[0].equals("GET") && path.equals("/frame.jpg") && jpeg != null && state.equals("READY")) {
                body = jpeg; type = "image/jpeg";
            } else if (parts[0].equals("POST") && path.equals("/exposure-reset")) {
                resetExposure(); body = "{\"ok\":true}".getBytes("UTF-8");
            } else { code = 404; body = "{\"error\":\"not available\"}".getBytes("UTF-8"); }
            OutputStream output = connection.getOutputStream();
            output.write(("HTTP/1.1 " + code + " Response\r\nContent-Type: " + type +
                "\r\nContent-Length: " + body.length + "\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n").getBytes("UTF-8"));
            output.write(body); output.flush();
        } catch (Exception ignored) { /* Disconnected browser request. */ }
    }
}
