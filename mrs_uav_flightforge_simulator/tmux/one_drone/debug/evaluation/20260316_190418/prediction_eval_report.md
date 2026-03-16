# Prediction evaluation report

## Prediction vs ground truth

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 1232 | 0.561 | 0.769 | 1.133 | 1.134 | 0.665 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Prediction vs known trajectory model

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 1232 | 4.691 | 5.414 | 5.113 | 5.250 | 0.665 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Real trajectory consistency vs known model

| count | mean error [m] | max error [m] |
| ---: | ---: | ---: |
| 10136 | 4.476 | 8.005 |

## Worst proposed predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 181.135 | 26 | 4.724 | 5.113 | 8.334 | 8.334 | 3.324 |
| 2 | 158.389 | 26 | 4.046 | 4.429 | 7.419 | 7.419 | 3.089 |
| 3 | 120.603 | 26 | 3.406 | 3.752 | 6.369 | 6.369 | 2.713 |
| 4 | 178.232 | 26 | 2.554 | 2.795 | 4.683 | 4.683 | 1.958 |
| 5 | 105.014 | 26 | 2.375 | 2.584 | 4.276 | 4.276 | 1.758 |

## Worst baseline predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| - | - | - | - | - | - | - | - |

> Note: all metrics and plots are computed only on the circular phase of the trajectory.

## RViz topics

- predicted trajectory: `/target/predicted_trajectory`

## Artifacts

- JSON summary: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_190418/prediction_eval.json`
- Plot PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_190418/prediction_eval_plot.png`
- XY comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_190418/prediction_eval_xy.png`
- Per-sample CSV: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_190418/prediction_eval_samples.csv`
