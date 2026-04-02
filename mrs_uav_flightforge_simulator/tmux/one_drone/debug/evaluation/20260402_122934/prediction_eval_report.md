# Prediction evaluation report

## Prediction vs ground truth

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 1173 | 0.161 | 0.225 | 0.285 | 0.290 | 0.437 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Prediction vs known trajectory model

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 0 | n/a | n/a | n/a | n/a | n/a |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## ANEES consistency (3D position)

| samples | ANEES mean | ANEES max | expected value | estimate msgs | unmatched GT | tol [s] |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8227 | 3.002 | 28.060 | 3.000 | 1191 | 135 | 0.150 |

## Worst proposed predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 57.118 | 26 | 0.635 | 0.697 | 1.187 | 1.187 | 1.090 |
| 2 | 46.123 | 26 | 0.618 | 0.731 | 1.384 | 1.384 | 1.424 |
| 3 | 57.011 | 26 | 0.615 | 0.686 | 1.204 | 1.204 | 1.155 |
| 4 | 46.057 | 26 | 0.607 | 0.721 | 1.378 | 1.378 | 1.427 |
| 5 | 46.393 | 26 | 0.602 | 0.702 | 1.319 | 1.319 | 1.412 |

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

- JSON summary: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260402_122934/prediction_eval.json`
- Plot PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260402_122934/prediction_eval_plot.png`
- XY comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260402_122934/prediction_eval_xy.png`
- XYZ comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260402_122934/prediction_eval_xyz.png`
- Distance error PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260402_122934/prediction_eval_distance.png`
- Per-sample CSV: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260402_122934/prediction_eval_samples.csv`
