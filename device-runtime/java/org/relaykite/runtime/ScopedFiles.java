package org.relaykite.runtime;
import java.io.File;
import java.io.IOException;
import java.util.regex.Pattern;

/** Resolve only a regular nonce-named file within the owned sharing cache. */
public final class ScopedFiles {
    private static final Pattern TOKEN=Pattern.compile("[a-f0-9]{32}\\.[a-z0-9]{1,12}");
    public static File resolve(File root,String token) throws IOException {
        if(token==null || !TOKEN.matcher(token).matches())throw new IOException("Invalid scoped file token");
        File canonicalRoot=root.getCanonicalFile();
        File requested=new File(canonicalRoot,token);
        File resolved=requested.getCanonicalFile();
        if(!resolved.getParentFile().equals(canonicalRoot) || !resolved.equals(requested) || !resolved.isFile())
            throw new IOException("Scoped file is unavailable");
        return resolved;
    }
    private ScopedFiles(){}
}
