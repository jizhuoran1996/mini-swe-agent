/* Out-of-tree lucene-core API consumer (core profile): create, query, mutate,
 * close/reopen across processes, then append a second batch. Uses only classes
 * shipped in lucene-core (null analyzer + pre-tokenized StringField terms). */
import java.nio.file.Path;
import java.nio.file.Paths;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.Field;
import org.apache.lucene.document.StringField;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.IndexWriter;
import org.apache.lucene.index.IndexWriterConfig;
import org.apache.lucene.index.Term;
import org.apache.lucene.search.IndexSearcher;
import org.apache.lucene.search.TermQuery;
import org.apache.lucene.search.TopDocs;
import org.apache.lucene.store.Directory;
import org.apache.lucene.store.FSDirectory;public class LuceneConsumer {
    static Directory dir;

    public static void main(String[] args) throws Exception {
        String mode = args[0];
        Path p = Paths.get(args[1]);
        dir = FSDirectory.open(p);
        try {
            System.out.println("lucene-core loaded from " +
                IndexWriter.class.getProtectionDomain().getCodeSource().getLocation());
            switch (mode) {
                case "create": create(); break;
                case "query":  query();  break;
                case "mutate": mutate(); break;
                case "verify": verify(); break;
                case "batch2": batch2(); break;
                default: throw new IllegalArgumentException(mode);
            }
        } finally {
            dir.close();
        }
    }

    /* null analyzer => every field must carry pre-analyzed terms (StringField). */
    static IndexWriter writer() throws Exception {
        IndexWriterConfig cfg = new IndexWriterConfig(null);
        cfg.setOpenMode(IndexWriterConfig.OpenMode.CREATE_OR_APPEND);
        return new IndexWriter(dir, cfg);
    }

    static void add(IndexWriter w, String id, String tag) throws Exception {
        Document d = new Document();
        d.add(new StringField("id", id, Field.Store.YES));
        d.add(new StringField("tag", tag, Field.Store.YES));
        w.addDocument(d);
    }

    static int count(String field, String term) throws Exception {
        DirectoryReader r = DirectoryReader.open(dir);
        try {
            IndexSearcher s = new IndexSearcher(r);
            TopDocs td = s.search(new TermQuery(new Term(field, term)), 10);
            return (int) td.totalHits.value;
        } finally { r.close(); }
    }

    static void create() throws Exception {
        IndexWriter w = writer();
        add(w, "1", "alpha");
        add(w, "2", "alpha");
        add(w, "3", "beta");
        w.commit(); w.close();
        System.out.println("created docs=3");
    }

    static void query() throws Exception {
        int a = count("tag", "alpha");
        if (a != 2) throw new AssertionError("expected 2 alpha, got " + a);
        if (count("id", "3") != 1) throw new AssertionError("doc3 not found");
        System.out.println("query alpha=2 doc3=1 ok");
    }

    static void mutate() throws Exception {
        IndexWriter w = writer();
        Document d = new Document();
        d.add(new StringField("id", "1", Field.Store.YES));
        d.add(new StringField("tag", "gamma", Field.Store.YES));
        w.updateDocument(new Term("id", "1"), d);
        w.deleteDocuments(new Term("id", "2"));
        w.commit(); w.close();
        System.out.println("mutated update+delete ok");
    }

    static void verify() throws Exception {
        if (count("tag", "alpha") != 0) throw new AssertionError("alpha still present");
        if (count("tag", "gamma") != 1) throw new AssertionError("gamma missing");
        if (count("id", "2") != 0) throw new AssertionError("deleted doc2 still present");
        System.out.println("verify ok alpha=0 gamma=1 doc2=0");
    }

    static void batch2() throws Exception {
        IndexWriter w = writer();
        add(w, "4", "alpha");
        add(w, "5", "alpha");
        w.commit(); w.close();
        if (count("id", "3") != 1) throw new AssertionError("doc3 missing after batch2");
        int a = count("tag", "alpha");
        if (a != 2) throw new AssertionError("expected 2 alpha in batch2, got " + a);
        if (count("tag", "gamma") != 1) throw new AssertionError("gamma lost in batch2");
        System.out.println("batch2 ok alpha=2 doc3=1 gamma=1");
    }
}
