/* Out-of-tree Lucene core API consumer: create, query, mutate, reopen, batch2. */
import java.nio.file.Path;
import java.nio.file.Paths;
import org.apache.lucene.analysis.standard.StandardAnalyzer;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.Field;
import org.apache.lucene.document.StringField;
import org.apache.lucene.document.TextField;
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
    static StandardAnalyzer an;

    public static void main(String[] args) throws Exception {
        String mode = args[0];
        Path p = Paths.get(args[1]);
        an = new StandardAnalyzer();
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
            an.close();
        }
    }

    static IndexWriter writer() throws Exception {
        IndexWriterConfig cfg = new IndexWriterConfig(an);
        cfg.setOpenMode(IndexWriterConfig.OpenMode.CREATE_OR_APPEND);
        return new IndexWriter(dir, cfg);
    }

    static void add(IndexWriter w, String id, String title, String body) throws Exception {
        Document d = new Document();
        d.add(new StringField("id", id, Field.Store.YES));
        d.add(new TextField("title", title, Field.Store.YES));
        d.add(new TextField("body", body, Field.Store.YES));
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
        add(w, "1", "hello world", "the quick brown fox");
        add(w, "2", "hello there", "lazy dog sleeps");
        add(w, "3", "goodbye", "nothing to see");
        w.commit(); w.close();
        System.out.println("created docs=3");
    }

    static void query() throws Exception {
        int h = count("title", "hello");
        if (h != 2) throw new AssertionError("expected 2 hello, got " + h);
        System.out.println("query hello=2 ok");
    }

    static void mutate() throws Exception {
        IndexWriter w = writer();
        Document d = new Document();
        d.add(new StringField("id", "1", Field.Store.YES));
        d.add(new TextField("title", "updated title", Field.Store.YES));
        d.add(new TextField("body", "changed content", Field.Store.YES));
        w.updateDocument(new Term("id", "1"), d);
        w.deleteDocuments(new Term("id", "2"));
        w.commit(); w.close();
        System.out.println("mutated update+delete ok");
    }

    static void verify() throws Exception {
        int h = count("title", "hello");
        if (h != 0) throw new AssertionError("expected 0 hello after mutation, got " + h);
        int u = count("title", "updated");
        if (u != 1) throw new AssertionError("expected 1 updated, got " + u);
        System.out.println("verify ok");
    }

    static void batch2() throws Exception {
        IndexWriter w = writer();
        add(w, "4", "hello again", "second batch");
        add(w, "5", "hello extra", "more docs");
        w.commit(); w.close();
        if (count("id", "3") != 1) throw new AssertionError("doc3 missing after batch2");
        int h = count("title", "hello");
        if (h != 2) throw new AssertionError("expected 2 hello in batch2, got " + h);
        System.out.println("batch2 ok hello=2 doc3 present");
    }
}
