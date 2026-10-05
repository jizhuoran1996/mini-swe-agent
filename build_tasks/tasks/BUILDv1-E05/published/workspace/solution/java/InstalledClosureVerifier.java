import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;

import org.elasticsearch.common.Strings;
import org.elasticsearch.index.query.BoolQueryBuilder;
import org.elasticsearch.index.query.QueryBuilder;
import org.elasticsearch.index.query.QueryBuilders;
import org.elasticsearch.index.query.TermQueryBuilder;
import org.elasticsearch.xcontent.ToXContent;
import org.elasticsearch.xcontent.XContentBuilder;
import org.elasticsearch.xcontent.XContentFactory;

/**
 * Fresh root-style consumer for a delivered Elasticsearch SDK install.
 *
 * It recursively discovers EVERY delivered *.jar under INSTALL_ROOT, builds an
 * isolated URLClassLoader from exactly those files and proves the essential
 * classes are loadable without the source tree or the Gradle cache.  It then
 * uses the real query APIs directly (the consumer is compiled against the
 * delivered closure too):
 *
 *   * a term query on field "state" with value "independent" is built and its
 *     field name and value are asserted;
 *   * a bool query is assembled with exactly one must clause and one filter
 *     clause and both list counts and element identities are asserted;
 *   * the bool query is serialised with the ORIGINAL Elasticsearch public JSON
 *     builder extraction API org.elasticsearch.common.Strings.toString(
 *     XContentBuilder), which closes the builder and reads its original UTF-8
 *     output stream - the JSON actually emitted by bool.toXContent(...);
 *   * BoolQueryBuilder.toString() is asserted separately.
 *
 * Serialisation calling sequence (important): upstream
 * org.elasticsearch.index.query.AbstractQueryBuilder.toXContent(...) already
 * performs builder.startObject(), doXContent(...) and builder.endObject(),
 * emitting one complete root object.  The consumer therefore must NOT wrap
 * that call in another start/end object pair; doing so is exactly what produced
 * com.fasterxml.jackson.core.JsonGenerationException: Can not start an object,
 * expecting field name.  The consumer calls toXContent(...) once on a fresh
 * builder and lets the query builder write its own complete root object.
 *
 * The builder's own Object.toString() (java.lang.Object identity, e.g.
 * org.elasticsearch.xcontent.XContentBuilder@723e88f9) is NOT the emitted JSON;
 * the original public extraction API org.elasticsearch.common.Strings.toString
 * must be used instead.  It is defined as:
 *
 *     public static String toString(XContentBuilder xContentBuilder) {
 *         xContentBuilder.close();
 *         OutputStream stream = xContentBuilder.getOutputStream();
 *         if (stream instanceof ByteArrayOutputStream baos) {
 *             return baos.toString(StandardCharsets.UTF_8);
 *         } else {
 *             return ((BytesStream) stream).bytes().utf8ToString();
 *         }
 *     }
 *
 * Usage: InstalledClosureVerifier <install-dir>
 */
public final class InstalledClosureVerifier {

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: InstalledClosureVerifier <install-dir>");
            System.exit(2);
        }
        Path install = Path.of(args[0]).toAbsolutePath().normalize();

        List<Path> jars = new ArrayList<>();
        try (Stream<Path> walk = Files.walk(install)) {
            walk.filter(Files::isRegularFile)
                .filter(p -> p.getFileName().toString().endsWith(".jar"))
                .forEach(jars::add);
        }
        Collections.sort(jars);
        if (jars.isEmpty()) {
            System.err.println("FAIL: no delivered jars under " + install);
            System.exit(1);
        }
        System.out.println("delivered-jars=" + jars.size());
        for (Path jar : jars) {
            System.out.println("  " + install.relativize(jar));
        }

        URL[] urls = new URL[jars.size()];
        for (int i = 0; i < jars.size(); i++) {
            urls[i] = jars.get(i).toUri().toURL();
        }

        // Sanity: essential classes loadable from the delivered closure alone.
        try (URLClassLoader loader = new URLClassLoader(urls, ClassLoader.getPlatformClassLoader())) {
            for (String name : new String[]{
                    "org.elasticsearch.index.query.QueryBuilders",
                    "org.elasticsearch.index.query.TermQueryBuilder",
                    "org.elasticsearch.index.query.BoolQueryBuilder",
                    "org.elasticsearch.common.Strings",
                    "org.elasticsearch.xcontent.ToXContentObject"}) {
                Class.forName(name, false, loader);
            }
        }

        // Real query-package API usage, compiled against the delivered closure.
        TermQueryBuilder term = QueryBuilders.termQuery("state", "independent");
        if (!"state".equals(term.fieldName())) {
            fail("term fieldName was not state");
        }
        if (!"independent".equals(String.valueOf(term.value()))) {
            fail("term value was not independent");
        }

        QueryBuilder filterQuery = QueryBuilders.existsQuery("available");
        BoolQueryBuilder bool = QueryBuilders.boolQuery().must(term).filter(filterQuery);
        if (bool.must().size() != 1) {
            fail("bool must list size was not 1");
        }
        if (bool.filter().size() != 1) {
            fail("bool filter list size was not 1");
        }
        if (bool.must().get(0) != term) {
            fail("bool must element identity mismatch");
        }
        if (bool.filter().get(0) != filterQuery) {
            fail("bool filter element identity mismatch");
        }

        // AbstractQueryBuilder.toXContent already writes startObject/doXContent/
        // endObject, so calling it once yields one complete root object.  Do not
        // add an outer startObject/endObject pair here.
        //
        // The emitted JSON is extracted with the ORIGINAL Elasticsearch public
        // API org.elasticsearch.common.Strings.toString(XContentBuilder).  A
        // plain builder.toString() would return java.lang.Object identity
        // (org.elasticsearch.xcontent.XContentBuilder@...), not JSON.
        XContentBuilder builder = XContentFactory.jsonBuilder();
        bool.toXContent(builder, ToXContent.EMPTY_PARAMS);
        String json = Strings.toString(builder);
        System.out.println("bool-json=" + json);
        if (!json.contains("independent")) {
            fail("serialised bool query missing term value independent");
        }
        if (!json.contains("exists")) {
            fail("serialised bool query missing exists filter");
        }

        // Separate real branch: BoolQueryBuilder.toString() must independently
        // contain the same query content.
        String text = bool.toString();
        System.out.println("bool-toString=" + text);
        if (!text.contains("independent")) {
            fail("BoolQueryBuilder.toString missing independent");
        }
        if (!text.contains("exists")) {
            fail("BoolQueryBuilder.toString missing exists");
        }

        System.out.println("INSTALLED_CLOSURE_VERIFIED_OK");
    }

    private static void fail(String message) {
        System.err.println("FAIL: " + message);
        System.exit(1);
    }
}
