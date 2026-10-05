#define PY_SSIZE_T_CLEAN
#include <Python.h>
#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
#include <numpy/arrayobject.h>

static PyObject *cext_sum(PyObject *self, PyObject *args) {
    PyObject *obj;
    if (!PyArg_ParseTuple(args, "O", &obj)) {
        return NULL;
    }
    PyArrayObject *arr =
        (PyArrayObject *)PyArray_FROM_OTF(obj, NPY_DOUBLE, NPY_ARRAY_IN_ARRAY);
    if (arr == NULL) {
        return NULL;
    }
    npy_intp n = PyArray_SIZE(arr);
    double *data = (double *)PyArray_DATA(arr);
    double total = 0.0;
    for (npy_intp i = 0; i < n; ++i) {
        total += data[i];
    }
    Py_DECREF(arr);
    return PyFloat_FromDouble(total);
}

static PyMethodDef methods[] = {
    {"cext_sum", cext_sum, METH_VARARGS, "Sum a double array via the NumPy C API"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT, "consumer_cext",
    "Minimal NumPy C-API consumer built against the delivered headers.", -1, methods
};

PyMODINIT_FUNC PyInit_consumer_cext(void) {
    import_array();
    return PyModule_Create(&moduledef);
}
