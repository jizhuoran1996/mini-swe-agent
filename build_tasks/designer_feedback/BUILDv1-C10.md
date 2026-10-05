RealofficialVTK9.4.2 CMakeconfigureerror:TheVTK::octree dependencyismissingforVTK::RenderingLabel. ENABLE_TESTS WANT knownissue; configureexplicitlyenableVTK_octree YES asdocumented. Do notdisabletests, droprequiredgeometry/IO modules orchangeexpected outputs. Core profile requiredmodulesexactmanifest; dependencies may beexplicitlyenabled. Default render groupsnotmandatorybuttestingdependencyclosurecurrentlyincludesRenderingLabel. Keep nonempty officialCommon/Filters/IOtest selectors andfresh privateSDKconsumer.

CRITICAL REVIEW: latestExternalData_Add_Targetsuppressionpatch is rejected. Do not replaceANYupstreamCMakefunctionwithdummy/no-op, alterofficialbaselines, orskiprequiredtests. Thisisnotallowedmocking. Officialsupported data exclusion option if present may beused ONLYtoomitautomaticfetch ofUNUSEDdata atALLbuildtime; missingfixturesforfrozencoretests mustremainrequired. Frozenmodulesfull8SDK+nonemptyupstreamgeometry/IOtestsubset mustremain. Exactsource snippetsbelow:
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/CMake/vtkExternalData.cmake

if(DEFINED ENV{DASHBOARD_TEST_FROM_CTEST})
  # Dashboard builds always need data.
  set(VTK_DATA_EXCLUDE_FROM_ALL OFF)
endif()

if(NOT DEFINED VTK_DATA_EXCLUDE_FROM_ALL)
  if(EXISTS "${VTK_SOURCE_DIR}/.ExternalData/config/exclude-from-all")
    # Configuration left by developer setup script.
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/CMake/vtkExternalData.cmake
  set(VTK_DATA_EXCLUDE_FROM_ALL OFF)
endif()

if(NOT DEFINED VTK_DATA_EXCLUDE_FROM_ALL)
  if(EXISTS "${VTK_SOURCE_DIR}/.ExternalData/config/exclude-from-all")
    # Configuration left by developer setup script.
    file(STRINGS "${VTK_SOURCE_DIR}/.ExternalData/config/exclude-from-all"
      vtk_data_exclude_from_all_default LIMIT_COUNT 1 LIMIT_INPUT 1024)
  elseif(DEFINED "ENV{VTK_DATA_EXCLUDE_FROM_ALL}")
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/CMake/vtkExternalData.cmake
    # Configuration left by developer setup script.
    file(STRINGS "${VTK_SOURCE_DIR}/.ExternalData/config/exclude-from-all"
      vtk_data_exclude_from_all_default LIMIT_COUNT 1 LIMIT_INPUT 1024)
  elseif(DEFINED "ENV{VTK_DATA_EXCLUDE_FROM_ALL}")
    set(vtk_data_exclude_from_all_default
      "$ENV{VTK_DATA_EXCLUDE_FROM_ALL}")
  else()
    set(vtk_data_exclude_from_all_default OFF)
  endif()
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/CMake/vtkExternalData.cmake
      vtk_data_exclude_from_all_default LIMIT_COUNT 1 LIMIT_INPUT 1024)
  elseif(DEFINED "ENV{VTK_DATA_EXCLUDE_FROM_ALL}")
    set(vtk_data_exclude_from_all_default
      "$ENV{VTK_DATA_EXCLUDE_FROM_ALL}")
  else()
    set(vtk_data_exclude_from_all_default OFF)
  endif()
  option(VTK_DATA_EXCLUDE_FROM_ALL "Exclude test data download from default 'all' target." "${vtk_data_exclude_from_all_default}")
  mark_as_advanced(VTK_DATA_EXCLUDE_FROM_ALL)
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/CMake/vtkExternalData.cmake
  else()
    set(vtk_data_exclude_from_all_default OFF)
  endif()
  option(VTK_DATA_EXCLUDE_FROM_ALL "Exclude test data download from default 'all' target." "${vtk_data_exclude_from_all_default}")
  mark_as_advanced(VTK_DATA_EXCLUDE_FROM_ALL)
endif()
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/CMake/vtkExternalData.cmake
    set(vtk_data_exclude_from_all_default OFF)
  endif()
  option(VTK_DATA_EXCLUDE_FROM_ALL "Exclude test data download from default 'all' target." "${vtk_data_exclude_from_all_default}")
  mark_as_advanced(VTK_DATA_EXCLUDE_FROM_ALL)
endif()
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/CMakeLists.txt
if (VTK_BUILD_TESTING)
  # Create target to download data from the VTKData group.  This must come after
  # all tests have been added that reference the group, so we put it last.
  ExternalData_Add_Target(VTKData)

  if (VTK_DATA_EXCLUDE_FROM_ALL)
    set_property(TARGET VTKData PROPERTY EXCLUDE_FROM_ALL 1)
    if (NOT VTK_DATA_EXCLUDE_FROM_ALL_NO_WARNING)
      message(WARNING
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/CMakeLists.txt
  # all tests have been added that reference the group, so we put it last.
  ExternalData_Add_Target(VTKData)

  if (VTK_DATA_EXCLUDE_FROM_ALL)
    set_property(TARGET VTKData PROPERTY EXCLUDE_FROM_ALL 1)
    if (NOT VTK_DATA_EXCLUDE_FROM_ALL_NO_WARNING)
      message(WARNING
        "VTK_DATA_EXCLUDE_FROM_ALL is ON so test data (needed because "
        "VTK_BUILD_TESTING is ON) may not be available without manually "
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/CMakeLists.txt

  if (VTK_DATA_EXCLUDE_FROM_ALL)
    set_property(TARGET VTKData PROPERTY EXCLUDE_FROM_ALL 1)
    if (NOT VTK_DATA_EXCLUDE_FROM_ALL_NO_WARNING)
      message(WARNING
        "VTK_DATA_EXCLUDE_FROM_ALL is ON so test data (needed because "
        "VTK_BUILD_TESTING is ON) may not be available without manually "
        "building the 'VTKData' target.")
    endif ()
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/CMakeLists.txt
    set_property(TARGET VTKData PROPERTY EXCLUDE_FROM_ALL 1)
    if (NOT VTK_DATA_EXCLUDE_FROM_ALL_NO_WARNING)
      message(WARNING
        "VTK_DATA_EXCLUDE_FROM_ALL is ON so test data (needed because "
        "VTK_BUILD_TESTING is ON) may not be available without manually "
        "building the 'VTKData' target.")
    endif ()
  endif ()

VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/Testing/External/CMakeLists.txt

# Create target to download data from the VTKData group.  This must come after
# all tests have been added that reference the group, so we put it last.
ExternalData_Add_Target(VTKData)
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/Testing/ExternalWasm/CMakeLists.txt

# Create target to download data from the VTKData group.  This must come after
# all tests have been added that reference the group, so we put it last.
ExternalData_Add_Target(VTKData)
VTK-13acb1a5dd0ad7f7635f2511f44e599733643d06/Testing/ExternalWheel/CMakeLists.txt

# Create target to download data from the VTKData group.  This must come after
# all tests have been added that reference the group, so we put it last.
ExternalData_Add_Target(VTKData)
SetStandAlonegroupDONT_WANT toavoidunrequestedallmodules, explicitlyenableallrequiredSDKmodules andlegitTestDependencies. Keeprequiredtests untouched. Alternatives buildexplicitactualmodule/testtargets(notallunusedVTKbaselines)oracquireofficialExternalDatabyhash. Neverneutralize fetch function.
