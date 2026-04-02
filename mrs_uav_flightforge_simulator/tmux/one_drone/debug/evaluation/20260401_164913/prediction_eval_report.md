# Prediction evaluation report

## Prediction vs ground truth

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 651 | 0.260 | 0.313 | 0.404 | 0.406 | 0.403 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Prediction vs known trajectory model

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 610 | 0.982 | 1.195 | 1.899 | 1.914 | 0.405 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Real trajectory consistency vs known model

| count | mean error [m] | max error [m] |
| ---: | ---: | ---: |
| 4066 | 0.062 | 0.310 |

## ANEES consistency (3D position)

| samples | ANEES mean | ANEES max | expected value | estimate msgs | unmatched GT | tol [s] |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4362 | 7.043 | 23.858 | 3.000 | 669 | 97 | 0.150 |

## Worst proposed predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 61.538 | 26 | 0.642 | 0.655 | 0.883 | 0.883 | 0.453 |
| 2 | 43.393 | 26 | 0.630 | 0.644 | 0.876 | 0.876 | 0.469 |
| 3 | 60.595 | 26 | 0.623 | 0.635 | 0.853 | 0.853 | 0.440 |
| 4 | 43.325 | 26 | 0.621 | 0.636 | 0.873 | 0.873 | 0.479 |
| 5 | 60.063 | 26 | 0.612 | 0.630 | 0.887 | 0.887 | 0.514 |

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

- JSON summary: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_164913/prediction_eval.json`
- Plot PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_164913/prediction_eval_plot.png`
- XY comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_164913/prediction_eval_xy.png`
- XYZ comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_164913/prediction_eval_xyz.png`
- Distance error PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_164913/prediction_eval_distance.png`
- Per-sample CSV: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_164913/prediction_eval_samples.csv`
