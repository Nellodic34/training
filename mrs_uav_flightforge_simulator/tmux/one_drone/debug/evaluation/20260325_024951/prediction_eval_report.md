# Prediction evaluation report

## Prediction vs ground truth

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 1302 | 0.385 | 0.488 | 0.765 | 0.765 | 0.537 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Prediction vs known trajectory model

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 1180 | 0.866 | 1.080 | 1.785 | 1.797 | 0.557 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Real trajectory consistency vs known model

| count | mean error [m] | max error [m] |
| ---: | ---: | ---: |
| 4276 | 0.058 | 0.358 |

## ANEES consistency (3D position)

| samples | ANEES mean | ANEES max | expected value | estimate msgs | unmatched GT | tol [s] |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3311 | 3.279 | 17.963 | 3.000 | 1336 | 1558 | 0.100 |

## Worst proposed predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 68.153 | 26 | 1.259 | 1.328 | 2.028 | 2.028 | 0.994 |
| 2 | 68.153 | 26 | 1.259 | 1.328 | 2.028 | 2.028 | 0.994 |
| 3 | 68.081 | 26 | 1.243 | 1.316 | 2.034 | 2.034 | 1.018 |
| 4 | 68.081 | 26 | 1.243 | 1.316 | 2.034 | 2.034 | 1.018 |
| 5 | 68.014 | 26 | 1.225 | 1.302 | 2.033 | 2.033 | 1.031 |

## Worst baseline predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| - | - | - | - | - | - | - | - |

> Note: metrics and plots are computed on all timestamps where prediction and reference can be matched.

## RViz topics

- predicted trajectory: `/target/predicted_trajectory`
- known trajectory input: `/target/known_trajectory_path`
- estimate odometry: `/target/odometry_estimate`

## Artifacts

- JSON summary: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260325_024951/prediction_eval.json`
- Plot PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260325_024951/prediction_eval_plot.png`
- XY comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260325_024951/prediction_eval_xy.png`
- XYZ comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260325_024951/prediction_eval_xyz.png`
- Per-sample CSV: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260325_024951/prediction_eval_samples.csv`
