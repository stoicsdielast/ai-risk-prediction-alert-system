import numpy as np
import pandas as pd

from ml.benchmark03 import feasible_policy, select_choices
from ml.config import TARGET


def test_infeasible_policy_never_forces_a_detection():
    data = pd.DataFrame({TARGET: [0, 0, 1]})
    policy, feasible = feasible_policy(data, [0.9, 0.8, 0.1], 1.0)
    assert not feasible
    assert policy["threshold"] > 1
    assert not (np.array([0.9, 0.8, 0.1]) >= policy["threshold"]).any()


def test_selection_prioritizes_feasible_station_recall_over_brier():
    table = pd.DataFrame([
        dict(candidate="best_brier", family="a", feasible=True, station_macro_recall=.1, recall=.2, pr_auc_average_precision=.8, brier=.01),
        dict(candidate="best_detection", family="a", feasible=True, station_macro_recall=.5, recall=.4, pr_auc_average_precision=.4, brier=.1),
        dict(candidate="over_budget", family="b", feasible=False, station_macro_recall=1., recall=1., pr_auc_average_precision=.9, brier=.001),
    ])
    choices = select_choices(table)
    assert choices["overall"] == "best_detection"
    assert choices["families"] == {"a": "best_detection", "b": "over_budget"}
    assert choices["diagnostic_only_ineligible_on_H1"] == ["over_budget"]
