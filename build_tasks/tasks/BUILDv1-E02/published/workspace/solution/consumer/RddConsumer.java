import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.apache.spark.SparkConf;
import org.apache.spark.api.java.JavaPairRDD;
import org.apache.spark.api.java.JavaRDD;
import org.apache.spark.api.java.JavaSparkContext;

/** Independent local RDD consumer run exclusively against the freshly built
 *  Spark core artifacts staged under the delivered INSTALL_ROOT. */
public final class RddConsumer {
  public static void main(String[] args) {
    SparkConf conf = new SparkConf()
        .setAppName("RddConsumer")
        .setMaster("local[2]")
        .set("spark.ui.enabled", "false")
        .set("spark.driver.host", "127.0.0.1")
        .set("spark.driver.bindAddress", "127.0.0.1");

    try (JavaSparkContext sc = new JavaSparkContext(conf)) {
      // Small parallel RDD arithmetic.
      JavaRDD<Integer> nums = sc.parallelize(Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), 2);
      int sum = nums.reduce(Integer::sum);
      long evens = nums.filter(x -> x % 2 == 0).count();
      int max = nums.reduce(Math::max);
      int partitions = nums.getNumPartitions();
      if (sum != 55) {
        throw new IllegalStateException("sum mismatch: " + sum);
      }
      if (evens != 5) {
        throw new IllegalStateException("even count mismatch: " + evens);
      }
      if (max != 10) {
        throw new IllegalStateException("max mismatch: " + max);
      }
      if (partitions != 2) {
        throw new IllegalStateException("partition count mismatch: " + partitions);
      }

      // Larger parallel transform with a 4-way partition split.
      List<Integer> range = new ArrayList<>();
      for (int i = 1; i <= 100; i++) {
        range.add(i);
      }
      JavaRDD<Integer> doubled = sc.parallelize(range, 4).map(x -> x * 2);
      int total = doubled.reduce(Integer::sum);
      if (doubled.getNumPartitions() != 4) {
        throw new IllegalStateException("doubled partition count mismatch");
      }
      if (total != 10100) {
        throw new IllegalStateException("doubled sum mismatch: " + total);
      }

      // A shuffle stage to exercise the scheduler machinery.
      JavaPairRDD<Integer, Integer> pairs = sc.parallelize(range, 4).mapToPair(x -> new scala.Tuple2<>(x % 3, x));
      long groupCount = pairs.groupByKey().count();
      if (groupCount != 3) {
        throw new IllegalStateException("group count mismatch: " + groupCount);
      }

      System.out.println("RDD_CONSUMER_OK sum=" + sum + " evens=" + evens + " max=" + max
          + " partitions=" + partitions + " doubled_total=" + total + " groups=" + groupCount);
    }
  }
}
