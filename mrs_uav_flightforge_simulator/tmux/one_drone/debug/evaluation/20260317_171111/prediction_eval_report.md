# Prediction evaluation report

## Prediction vs ground truth

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 673 | 0.506 | 0.692 | 1.105 | 1.106 | 0.687 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Prediction vs known trajectory model

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 613 | 0.560 | 0.842 | 1.239 | 1.239 | 0.714 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Real trajectory consistency vs known model

| count | mean error [m] | max error [m] |
| ---: | ---: | ---: |
| 4570 | 0.056 | 0.359 |

## ANEES consistency (3D position)

| samples | ANEES mean | ANEES max | expected value | estimate msgs | unmatched GT | tol [s] |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 675 | 4.563 | 51.437 | 3.000 | 701 | 4602 | 0.100 |

## Worst proposed predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 89.479 | 26 | 3.916 | 4.253 | 7.005 | 7.005 | 2.833 |
| 2 | 89.479 | 26 | 2.205 | 2.354 | 3.730 | 3.730 | 1.425 |
| 3 | 89.618 | 26 | 2.181 | 2.310 | 3.574 | 3.574 | 1.320 |
| 4 | 74.691 | 26 | 2.047 | 2.232 | 3.697 | 3.697 | 1.518 |
| 5 | 74.408 | 26 | 1.473 | 1.615 | 2.717 | 2.717 | 1.143 |

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

- JSON summary: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260317_171111/prediction_eval.json`
- Plot PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260317_171111/prediction_eval_plot.png`
- XY comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260317_171111/prediction_eval_xy.png`
- XYZ comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260317_171111/prediction_eval_xyz.png`
- Per-sample CSV: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260317_171111/prediction_eval_samples.csv`
