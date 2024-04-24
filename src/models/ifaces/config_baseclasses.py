"""This module defines an abstract class for models"""

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import yaml  # type: ignore

from src.utils.project_info import ExperimentInfo


@dataclass
class BaseConfig:
    """
    A data class to store model attributes
    """

    experiment_info: ExperimentInfo
    id_col_name: str
    target_col_name: str
    split_col_name: str
    class_names: list[str]
    optimize_hyperparams: bool
    n_calls_hyperparams_opt: int
    hyperparam_dimensions: dict
    neg_val: str
    negatives_sample_path: str
    tps_cleaned_csv_path: str
    random_state: int
    per_class_optimization: bool
    load_per_class_params_from: str
    reuse_existing_partial_results: bool

    @classmethod
    def load(cls, path_to_config: Union[str, Path]) -> dict:
        """
        This class function loads config from a configs folder
        :param path_to_config:
        :return: a dictionary loaded from the config yaml
        """
        with open(path_to_config, encoding="utf-8") as file:
            configs_dict = yaml.load(file, Loader=yaml.FullLoader)
            if "include" in configs_dict:
                included_file_path = configs_dict.pop("include")
                with open(
                    Path(path_to_config).parent / included_file_path,
                    "r",
                    encoding="utf-8",
                ) as included_file:
                    included_data = yaml.safe_load(included_file)
                    configs_dict.update(
                        {
                            key: val
                            for key, val in included_data.items()
                            if key not in configs_dict
                        }
                    )
        return configs_dict


@dataclass
class SklearnBaseConfig(BaseConfig):
    """
    A data class to store scikit-learn downstream models leveraging precomputed embeddings
    """

    max_train_negs_proportion: float
    save_trained_model: bool


@dataclass
class EmbSklearnBaseConfig(SklearnBaseConfig):
    """
    A data class to store the corresponding model attributes
    """

    representations_path: str


@dataclass
class FeaturesXGbConfig(SklearnBaseConfig):
    """
    A data class to store some Xgb model attributes
    """

    booster: str
    n_jobs: int
    objective: str
    fold_i: str
    reg_lambda: float
    gamma: float
    max_depth: int
    subsample: float
    colsample_bytree: float
    scale_pos_weight: float
    min_child_weight: int
    n_estimators: int


@dataclass
class FeaturesRandomForestConfig(SklearnBaseConfig):
    """
    A data class to store model attributes
    """

    n_estimators: int
    n_jobs: int
    class_weight: str
    max_depth: int
    fold_i: str


@dataclass
class EmbRandomForestConfig(EmbSklearnBaseConfig, FeaturesRandomForestConfig):
    """
    A data class to store the corresponding model attributes
    """


@dataclass
class EmbsXGbConfig(EmbSklearnBaseConfig, SklearnBaseConfig):
    """
    A data class to store the corresponding model attributes
    """