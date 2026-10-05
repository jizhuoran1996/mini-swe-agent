/* Independent C-API consumer: load a LightGBM model, predict a data file.
 * Linked against the freshly installed prefix (lib_lightgbm.so + LightGBM/c_api.h).
 */
#include <LightGBM/c_api.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char** argv) {
    if (argc < 5) {
        fprintf(stderr,
                "usage: %s <model_file> <data_file> <out_file> <num_iterations(0=all)> [has_header]\n",
                argv[0]);
        return 2;
    }
    const char* model_file = argv[1];
    const char* data_file = argv[2];
    const char* out_file = argv[3];
    int num_iter = atoi(argv[4]);
    int has_header = (argc > 5) ? atoi(argv[5]) : 0;

    int num_total = 0;
    BoosterHandle booster = NULL;
    int rc = LGBM_BoosterCreateFromModelfile(model_file, &num_total, &booster);
    if (rc != 0 || booster == NULL) {
        fprintf(stderr, "LGBM_BoosterCreateFromModelfile failed rc=%d\n", rc);
        return 1;
    }
    printf("LIGHTGBM_CONSUMER loaded=%s iterations=%d\n", model_file, num_total);

    if (num_iter <= 0 || num_iter > num_total) {
        num_iter = num_total;
    }

    rc = LGBM_BoosterPredictForFile(booster, data_file, has_header,
                                    C_API_PREDICT_NORMAL, 0, num_iter, "",
                                    out_file);
    if (rc != 0) {
        fprintf(stderr, "LGBM_BoosterPredictForFile failed rc=%d\n", rc);
        LGBM_BoosterFree(booster);
        return 1;
    }
    LGBM_BoosterFree(booster);
    printf("LIGHTGBM_CONSUMER predictions=%s num_iterations=%d\n", out_file, num_iter);
    return 0;
}
