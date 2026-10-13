package com.oai.androiduse;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

/** Owns ONLY a private Android VirtualDisplay. Exits and releases it after a 10-min lease. */
public final class DisplayEngine {
    private static Object virtualDisplay;
    private static Object imageReader;
    static String[] ownerArgs(String[] args) {
        String base="/data/local/tmp/codaki-portable-core";
        if(args.length==0)return new String[]{"CodakiPortableUse",base+"/lease-deadline"};
        if(args.length!=2)throw new IllegalArgumentException("Expected owned name and lease");
        String name=args[0];
        String expected;
        if(name.equals("CodakiPortableUse"))expected=base+"/lease-deadline";
        else if(name.matches("CodakiPortableUse_[a-f0-9]{32}"))expected=base+"/sessions/"+name.substring("CodakiPortableUse_".length())+"/lease-deadline";
        else throw new IllegalArgumentException("Invalid owned display name");
        if(!args[1].equals(expected))throw new IllegalArgumentException("Invalid owned lease path");
        return args;
    }

    private static Object invoke(Object object, String name, Class<?>[] types, Object... args) throws Exception {
        Method m = object.getClass().getMethod(name, types);
        m.setAccessible(true);
        return m.invoke(object, args);
    }
    private static Object invokeStatic(Class<?> clazz, String name, Class<?>[] types, Object... args) throws Exception {
        Method m = clazz.getDeclaredMethod(name, types);
        m.setAccessible(true);
        return m.invoke(null, args);
    }
    private static int flag(Class<?> clazz, String name) throws Exception {
        Field f = clazz.getDeclaredField(name);
        f.setAccessible(true);
        return f.getInt(null);
    }
    private static void cleanup() {
        try {
            if (virtualDisplay != null) invoke(virtualDisplay, "release", new Class<?>[0]);
        } catch (Exception ignored) {}
        try {
            if (imageReader != null) invoke(imageReader, "close", new Class<?>[0]);
        } catch (Exception ignored) {}
        virtualDisplay = null;
        imageReader = null;
    }

    public static void main(String[] args) {
        try {
            String[] owner=ownerArgs(args);
            invokeStatic(Class.forName("android.os.Looper"), "prepareMainLooper", new Class<?>[0]);
            Object thread = invokeStatic(Class.forName("android.app.ActivityThread"), "systemMain", new Class<?>[0]);
            Object context = invoke(thread, "getSystemContext", new Class<?>[0]);
            Object manager = invoke(context, "getSystemService", new Class<?>[]{String.class}, "display");
            if (manager == null) throw new IllegalStateException("DisplayManager unavailable");
            Class<?> dm = Class.forName("android.hardware.display.DisplayManager");
            int flags = 0;
            for (String name : new String[]{
                    "VIRTUAL_DISPLAY_FLAG_PUBLIC",
                    "VIRTUAL_DISPLAY_FLAG_PRESENTATION",
                    "VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY",
                    "VIRTUAL_DISPLAY_FLAG_DESTROY_CONTENT_ON_REMOVAL",
                    "VIRTUAL_DISPLAY_FLAG_SUPPORTS_TOUCH",
                    "VIRTUAL_DISPLAY_FLAG_TRUSTED",
                    "VIRTUAL_DISPLAY_FLAG_OWN_DISPLAY_GROUP",
                    "VIRTUAL_DISPLAY_FLAG_ALWAYS_UNLOCKED",
                    "VIRTUAL_DISPLAY_FLAG_OWN_FOCUS",
                    "VIRTUAL_DISPLAY_FLAG_STEAL_TOP_FOCUS_DISABLED"}) {
                flags |= flag(dm, name);
            }
            Class<?> ir = Class.forName("android.media.ImageReader");
            imageReader = invokeStatic(ir, "newInstance", new Class<?>[]{int.class,int.class,int.class,int.class},
                    720,1280,1,2);
            Object surface = invoke(imageReader,"getSurface",new Class<?>[0]);
            Class<?> surfaceType = Class.forName("android.view.Surface");
            virtualDisplay = invoke(manager, "createVirtualDisplay", new Class<?>[]{
                    String.class,int.class,int.class,int.class,surfaceType,int.class},
                    owner[0],720,1280,320,surface,flags);
            if (virtualDisplay == null) throw new IllegalStateException("VirtualDisplay unavailable");
            Object display = invoke(virtualDisplay,"getDisplay",new Class<?>[0]);
            int id = (Integer)invoke(display,"getDisplayId",new Class<?>[0]);
            int actualFlags = (Integer)invoke(display,"getFlags",new Class<?>[0]);
            if (id <= 0) throw new IllegalStateException("Virtual display ID invalid");
            System.out.println("CREATED " + id + " " + actualFlags);
            System.out.flush();
            Runtime.getRuntime().addShutdownHook(new Thread(DisplayEngine::cleanup));
            java.nio.file.Path lease=java.nio.file.Paths.get(owner[1]);
            while (java.nio.file.Files.exists(lease)) {
                long deadline=Long.parseLong(new String(java.nio.file.Files.readAllBytes(lease),java.nio.charset.StandardCharsets.US_ASCII).trim());
                if (System.currentTimeMillis()>=deadline) break;
                Thread.sleep(500L);
            }
        } catch (Throwable ex) {
            System.err.println("DISPLAY_ENGINE_ERROR " + ex.getClass().getName() + ": " + ex.getMessage());
            ex.printStackTrace(System.err);
        } finally {cleanup();}
    }
}
