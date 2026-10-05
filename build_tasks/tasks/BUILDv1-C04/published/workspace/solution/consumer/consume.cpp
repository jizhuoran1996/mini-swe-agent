#include <vips/vips8>
#include <iostream>

int main(int argc, char **argv) {
    if (VIPS_INIT(argv[0])) {
        std::cerr << "VIPS_INIT failed" << std::endl;
        return 1;
    }
    try {
        vips::VImage black = vips::VImage::black(200, 200,
            vips::VImage::option()->set("bands", 3));
        black.write_to_file("test.tif");

        vips::VImage in = vips::VImage::new_from_file("test.tif");
        std::cout << "input: " << in.width() << "x" << in.height()
                  << " bands=" << in.bands() << std::endl;

        vips::VImage cropped = in.crop(0, 0, 100, 100);
        vips::VImage scaled = cropped.resize(2.0);
        scaled.write_to_file("out.png");

        vips::VImage check = vips::VImage::new_from_file("out.png");
        if (check.width() != 200 || check.height() != 200) {
            std::cerr << "dimension mismatch: " << check.width()
                      << "x" << check.height() << std::endl;
            return 1;
        }
        if (check.bands() != 3) {
            std::cerr << "band mismatch: " << check.bands() << std::endl;
            return 1;
        }
        std::cout << "consumer OK: " << check.width() << "x" << check.height()
                  << " bands=" << check.bands() << std::endl;
    } catch (const std::exception &e) {
        std::cerr << "consumer error: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
