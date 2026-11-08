"""Event classifiers behind one interface, chosen by name (ClassifierConfig.name).

    fit(events, labels) / predict_proba(events) -> (n, n_classes), classes_ list
Each classifier decides what it reads from an Event: `features` (feature vector) or `rot`/`acc` (head-frame
signals, any length). Add one by writing a class and registering it in CLASSIFIERS.
"""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class FeatureLogReg:
    """Standardised physical features + multinomial logistic regression. Interpretable, fast, small."""

    def __init__(self, C=1.0, class_weight="balanced"):
        self.model = make_pipeline(StandardScaler(),
                                   LogisticRegression(C=C, class_weight=class_weight, max_iter=3000))

    def fit(self, events, labels):
        self.model.fit(np.stack([e.features for e in events]), np.asarray(labels))
        self.classes_ = list(self.model.classes_)
        return self

    def predict_proba(self, events):
        return self.model.predict_proba(np.stack([e.features for e in events]))


class MiniRocketSeq:
    """MiniRocket on the head-frame rotation + acceleration, resampled to a fixed length. Optional: needs `aeon`
    (not available for Python 3.15; use a Python 3.12 environment)."""

    def __init__(self, length=64):
        try:
            from aeon.classification.convolution_based import MiniRocketClassifier
        except ImportError as e:
            raise ImportError("MiniRocketSeq needs the 'aeon' package (Python <= 3.12).") from e
        self.length, self.model = length, MiniRocketClassifier(random_state=0)

    def _seq(self, events):
        out = []
        for e in events:
            x = np.hstack([e.rot, e.acc])
            ti = np.linspace(0, len(x) - 1, self.length)
            out.append(np.stack([np.interp(ti, np.arange(len(x)), x[:, j]) for j in range(x.shape[1])]))
        return np.stack(out)

    def fit(self, events, labels):
        self.model.fit(self._seq(events), np.asarray(labels))
        self.classes_ = list(self.model.classes_)
        return self

    def predict_proba(self, events):
        return self.model.predict_proba(self._seq(events))


CLASSIFIERS = {"logreg": FeatureLogReg, "minirocket": MiniRocketSeq}


def make_classifier(cfg):
    return CLASSIFIERS[cfg.name](**cfg.params)
