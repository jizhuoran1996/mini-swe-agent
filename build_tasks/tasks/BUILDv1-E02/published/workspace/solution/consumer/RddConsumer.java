import java.util.Arrays;
import java.util.List;
import org.apache.spark.SparkConf;
import org.apache.spark.api.java.JavaRDD;
import org.apache.spark.api.java.JavaSparkContext;

/** Independent local RDD consumer for the freshly built Spark core JARs. */
public final class RddConsumer {
  public static void main(String[] args) {
    SparkConf conf = new SparkConf()
        .setAppName("RddConsumer")
        .setMaster("local[2]")
        .set("spark.ui.enabled", "false")
        .set("spark.driver.host", "127.0.0.1")
        .set("spark.driver.bindAddress", "127.0.0.1");

    try (JavaSparkContext sc = new JavaSparkContext(conf)) {
      List<Integer> data = Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8, 9, 10);
      JavaRDD<Integer> nums = sc.parallelize(data, 2);

      int sum = nums.reduce(Integer::sum);
      if (sum != 55) {
        throw new IllegalStateException("sum mismatch: " + sum);
      }
      long evens = nums.filter(x -> x % 2 == 0).count();
      if (evens != 5) {
        throw new IllegalStateException("even count mismatch: " + evens);
      }
      long max = nums.reduce(Math::max);
      if (max != 10) {
        throw new IllegalStateException("max mismatch: " + max);
      }
      int partitions = nums.getNumPartitions();
      if (partitions != 2) {
        throw new IllegalStateException("partition count mismatch: " + partitions);
      }
      System.out.println("RDD_CONSUMER_OK sum=" + sum + " evens=" + evens
          + " max=" + max + " partitions=" + partitions);
    }
  }
}
