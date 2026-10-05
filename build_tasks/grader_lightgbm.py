"""Independent LightGBM C API training and serialized-model prediction."""
from grader_inside import INSTALL,WORK,execute,find_library


def lightgbm():
    source=WORK/'new_lgbm.cpp';source.write_text(r'''
#include <LightGBM/c_api.h>
#include <cmath>
#include <iostream>
int main(){float x[120],y[60];for(int i=0;i<60;i++){x[2*i]=i;x[2*i+1]=i%3;y[i]=i>=30;}
DatasetHandle d;const char*params="max_bin=31 min_data_in_bin=1 min_data_in_leaf=1 num_threads=2 verbose=-1";
if(LGBM_DatasetCreateFromMat(x,C_API_DTYPE_FLOAT32,60,2,1,params,nullptr,&d)||LGBM_DatasetSetField(d,"label",y,60,C_API_DTYPE_FLOAT32))return 1;
BoosterHandle b;if(LGBM_BoosterCreate(d,"objective=binary num_leaves=4 learning_rate=0.4 min_data_in_leaf=1 num_threads=2 verbosity=-1",&b))return 2;
for(int i=0;i<20;i++){int done;if(LGBM_BoosterUpdateOneIter(b,&done))return 3;}
double p[60];int64_t n;if(LGBM_BoosterPredictForMat(b,x,C_API_DTYPE_FLOAT32,60,2,1,C_API_PREDICT_NORMAL,0,-1,"num_threads=2",&n,p)||n!=60)return 4;
int correct=0;for(int i=0;i<60;i++)correct+=((p[i]>.5)==(y[i]>.5));if(correct<57)return 5;
if(LGBM_BoosterSaveModel(b,0,-1,0,"new-lgbm.txt"))return 6;BoosterHandle reload;int iterations;if(LGBM_BoosterCreateFromModelfile("new-lgbm.txt",&iterations,&reload))return 7;
double q[60];if(LGBM_BoosterPredictForMat(reload,x,C_API_DTYPE_FLOAT32,60,2,1,C_API_PREDICT_NORMAL,0,-1,"num_threads=2",&n,q))return 8;
for(int i=0;i<60;i++)if(std::abs(p[i]-q[i])>1e-12)return 9;LGBM_BoosterFree(reload);LGBM_BoosterFree(b);LGBM_DatasetFree(d);std::cout<<"new LightGBM C API train/save/reload passed "<<correct<<"/60\n";return 0;}
''')
    lib=find_library('_lightgbm');app=WORK/'new_lgbm';execute(['g++','-std=c++17',source,'-I',INSTALL/'include',lib,'-Wl,-rpath,'+str(lib.parent),'-o',app]);assert str(INSTALL) in execute(['ldd',app]).stdout.decode();return execute([app]).stdout.decode()

CONSUMERS={'BUILDv1-F09':lightgbm}
