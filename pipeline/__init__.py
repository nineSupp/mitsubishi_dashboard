"""Data cleaning, transformation and encoding pipeline (ported step by step from the project notebooks).

    notebooks/clean_data.ipynb          ->  pipeline/clean.py       Stage 1  Data Cleaning
    notebooks/data_transformation.ipynb ->  pipeline/transform.py   Stage 2  Transformation & Feature Engineering
    notebooks/data_encode.ipynb         ->  pipeline/encode.py      Stage 3  Encoding
    run_pipeline() chains the three stages and returns the final dataset (the same table as final_dataset_main.csv).

No Streamlit imports here, so the dashboard, the command line and the tests can all use it."""
from pipeline.run import run_pipeline, write_outputs, PipelineResult           # noqa: F401
from pipeline.readers import load_tables, detect_role                           # noqa: F401
