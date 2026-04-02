# Prediction evaluation report

## Prediction vs ground truth

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 636 | 0.164 | 0.204 | 0.296 | 0.296 | 0.336 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Prediction vs known trajectory model

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 590 | 1.056 | 1.273 | 2.080 | 2.096 | 0.332 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Real trajectory consistency vs known model

| count | mean error [m] | max error [m] |
| ---: | ---: | ---: |
| 4249 | 0.058 | 0.286 |

## ANEES consistency (3D position)

| samples | ANEES mean | ANEES max | expected value | estimate msgs | unmatched GT | tol [s] |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4425 | 2.333 | 16.344 | 3.000 | 651 | 252 | 0.150 |

## Worst proposed predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 33.844 | 26 | 0.506 | 0.586 | 1.061 | 1.061 | 0.986 |
| 2 | 33.916 | 26 | 0.503 | 0.577 | 1.031 | 1.031 | 0.943 |
| 3 | 33.987 | 26 | 0.499 | 0.568 | 0.999 | 0.999 | 0.895 |
| 4 | 33.774 | 26 | 0.496 | 0.580 | 1.067 | 1.067 | 1.012 |
| 5 | 34.100 | 26 | 0.494 | 0.553 | 0.949 | 0.949 | 0.822 |

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

- JSON summary: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_173637/prediction_eval.json`
- Plot PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_173637/prediction_eval_plot.png`
- XY comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_173637/prediction_eval_xy.png`
- XYZ comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_173637/prediction_eval_xyz.png`
- Distance error PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_173637/prediction_eval_distance.png`
- Per-sample CSV: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260401_173637/prediction_eval_samples.csv`
