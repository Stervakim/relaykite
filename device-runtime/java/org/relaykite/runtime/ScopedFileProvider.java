package org.relaykite.runtime;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import android.webkit.MimeTypeMap;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;

/** Non-exported, read-only provider; the system grants one selected URI. */
public final class ScopedFileProvider extends ContentProvider {
    private File root;
    public boolean onCreate(){
        if(getContext()==null)return false;
        root=new File(getContext().getCacheDir(),"shared");
        return root.isDirectory() || root.mkdirs();
    }
    private File selected(Uri uri) throws FileNotFoundException {
        if(!"content".equals(uri.getScheme()) || !"org.relaykite.runtime.files".equals(uri.getAuthority())
            || uri.getPathSegments().size()!=1 || uri.getQuery()!=null || uri.getFragment()!=null)
            throw new FileNotFoundException("Invalid scoped URI");
        try{return ScopedFiles.resolve(root,uri.getLastPathSegment());}
        catch(IOException error){throw new FileNotFoundException("Scoped file unavailable");}
    }
    public ParcelFileDescriptor openFile(Uri uri,String mode) throws FileNotFoundException {
        if(!"r".equals(mode))throw new FileNotFoundException("Read-only URI");
        return ParcelFileDescriptor.open(selected(uri),ParcelFileDescriptor.MODE_READ_ONLY);
    }
    public String getType(Uri uri){
        try{
            String name=selected(uri).getName();
            String type=MimeTypeMap.getSingleton().getMimeTypeFromExtension(name.substring(name.lastIndexOf('.')+1));
            return type==null?"application/octet-stream":type;
        }catch(FileNotFoundException error){return null;}
    }
    public Cursor query(Uri uri,String[] projection,String selection,String[] arguments,String sort){
        try{
            File file=selected(uri);
            String[] columns=projection==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:projection;
            MatrixCursor cursor=new MatrixCursor(columns,1);Object[] values=new Object[columns.length];
            for(int i=0;i<columns.length;i++){
                if(OpenableColumns.DISPLAY_NAME.equals(columns[i]))values[i]=file.getName();
                else if(OpenableColumns.SIZE.equals(columns[i]))values[i]=file.length();
            }
            cursor.addRow(values);return cursor;
        }catch(FileNotFoundException error){return new MatrixCursor(projection==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:projection,0);}
    }
    public Uri insert(Uri uri,ContentValues values){throw new UnsupportedOperationException("Read-only provider");}
    public int update(Uri uri,ContentValues values,String selection,String[] arguments){throw new UnsupportedOperationException("Read-only provider");}
    public int delete(Uri uri,String selection,String[] arguments){throw new UnsupportedOperationException("Read-only provider");}
}
