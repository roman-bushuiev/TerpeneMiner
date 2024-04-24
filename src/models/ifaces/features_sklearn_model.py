"""Module with interfaces for scikit-learn-compatible predictive models
built on top of numerical protein representations (features)"""
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np  # type: ignore
import pandas as pd  # type: ignore
import sklearn.base  # type: ignore
from sklearn.multioutput import MultiOutputClassifier  # type: ignore
from sklearn.preprocessing import MultiLabelBinarizer  # type: ignore

from .config_baseclasses import SklearnBaseConfig
from .model_baseclass import BaseModel

logger = logging.getLogger(__file__)
logging.basicConfig(level=logging.INFO)


class FeaturesSklearnModel(BaseModel):
    """Interfaces for scikit-learn-compatible predictive models
    built on top of numerical protein representations (features)"""

    def __init__(self, config: SklearnBaseConfig):
        super().__init__(config=config)
        try:
            self.per_class_optimization = self.config.per_class_optimization
            if self.per_class_optimization is None:
                self.per_class_optimization = False
        except AttributeError:
            self.per_class_optimization = False
        if self.per_class_optimization:
            self.class_2_classifier: dict = {}
        self.classifier: sklearn.base.BaseEstimator
        self.classes_ = None
        self.features_df = None

    def fit_core(self, train_df: pd.DataFrame, class_name: str = None):
        logger.info("Started fitting the model %s", self.__class__)
        assert isinstance(
            self.config, SklearnBaseConfig
        ), "EmbsSklearnModel model expects config of type SklearnBaseConfig"
        train_df_neg_all = train_df[
            train_df[self.config.target_col_name].map(
                lambda classes: self.config.neg_val in classes
            )
        ]
        negs_proportion = len(train_df_neg_all) / len(train_df)
        if negs_proportion > self.config.max_train_negs_proportion:
            positive_count = train_df[self.config.id_col_name].nunique() * (
                1 - negs_proportion
            )
            required_negs_count = (
                positive_count / (1 - self.config.max_train_negs_proportion)
                - positive_count
            )
            train_df_pos = train_df[
                train_df[self.config.target_col_name].map(
                    lambda classes: self.config.neg_val not in classes
                )
            ]
            train_df_neg = train_df_neg_all.sample(int(required_negs_count))
            train_df = pd.concat((train_df_pos, train_df_neg)).sample(frac=1.0)

        train_data = train_df.merge(self.features_df, on=self.config.id_col_name)

        if not self.per_class_optimization:
            # Multioutput version for global hyperparameters (the same for all classes)
            self.classifier = self.classifier_class(**self.get_model_specific_params())
            label_binarizer = MultiLabelBinarizer(classes=self.config.class_names)
            logger.info("Preparing multi-labels...")
            target = label_binarizer.fit_transform(
                train_data[self.config.target_col_name].values
            )
            logger.info("Fitting the model...")
            try:
                self.classifier.fit(
                    np.stack(train_data["Emb"].values),
                    target,
                )
            except ValueError:
                logger.info("Fall back to MultiOutputClassifier wrapper...")
                try:
                    n_jobs = self.get_model_specific_params()["n_jobs"]
                except KeyError:
                    n_jobs = -1
                self.classifier = MultiOutputClassifier(self.classifier, n_jobs=n_jobs)
                self.classifier.fit(
                    np.stack(train_data["Emb"].values),
                    target,
                )
            self.config.class_names = label_binarizer.classes_
        else:
            assert (
                class_name is not None
            ), "For per-class fitting the class name must be provided"
            model_specific_params = list(
                self.get_model_specific_params(class_name=class_name).items()
            )
            model_params = {
                param_name.replace(f"{class_name}_", ""): param_val
                for param_name, param_val in model_specific_params
            }
            is_class_specific_param_present = False
            for param_name, _ in model_specific_params:
                if class_name in param_name:
                    is_class_specific_param_present = True
                    break
            if is_class_specific_param_present:
                classifiier = self.classifier_class(**model_params)
                y_binary = train_data[self.config.target_col_name].map(
                    lambda x: int(class_name in x)
                )
                if sum(y_binary):
                    classifiier.fit(
                        np.stack(train_data["Emb"].values),
                        y_binary,
                    )
                    self.class_2_classifier[class_name] = classifiier

    def predict_proba(self, val_df: pd.DataFrame | np.ndarray) -> np.ndarray:
        if isinstance(val_df, pd.DataFrame):  # local validation
            assert isinstance(self.features_df, pd.DataFrame)
            test_df = val_df.merge(
                self.features_df, on=self.config.id_col_name, copy=False, how="left"
            ).set_index(self.config.id_col_name)
            average_emb = np.stack(self.features_df["Emb"].values).mean(axis=0)
            test_df["Emb"] = test_df["Emb"].map(
                lambda x: x if isinstance(x, np.ndarray) else average_emb
            )
            test_df = test_df.loc[val_df[self.config.id_col_name]]
            test_embs_np = np.stack(test_df["Emb"].values)
        elif isinstance(val_df, np.ndarray):  # test-time prediction
            test_embs_np = val_df
        else:
            raise NotImplementedError(
                f"Got {type(val_df)} as input to predict_proba function, "
                f"but only pd.DataFrame | np.ndarray are supported"
            )
        try:
            per_class_optimization = self.config.per_class_optimization
        except AttributeError:
            per_class_optimization = False
        val_proba_np = np.zeros((len(val_df), len(self.config.class_names)))
        if not per_class_optimization:
            logger.info(
                "Global model %s predicts proba for %d samples (%d features each)",
                str(self.classifier),
                *test_embs_np.shape,
            )
            y_pred_proba = self.classifier.predict_proba(test_embs_np)
            for class_i in range(len(self.config.class_names)):
                val_proba_np[:, class_i] = (
                    y_pred_proba[class_i][:, -1]
                    if isinstance(y_pred_proba, list)
                    else y_pred_proba[:, class_i]
                )
        else:
            for class_i, class_name in enumerate(self.config.class_names):
                if class_name in self.class_2_classifier:
                    val_proba_np[:, class_i] = self.class_2_classifier[
                        class_name
                    ].predict_proba(test_embs_np)[:, 1]

        return val_proba_np

    def save(self, experiment_output_folder: Optional[Path | str] = None):
        if experiment_output_folder is None:
            experiment_output_folder = self.output_root
        experiment_output_folder = Path(experiment_output_folder)
        with open(
            experiment_output_folder
            / f"model_fold_{self.config.experiment_info.fold}.pkl",
            "wb",
        ) as file:
            pickle.dump(self, file)
