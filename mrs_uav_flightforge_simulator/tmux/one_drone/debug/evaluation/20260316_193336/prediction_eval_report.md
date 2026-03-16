# Prediction evaluation report

## Prediction vs ground truth

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 1086 | 0.541 | 1.615 | 1.084 | 1.086 | 1.322 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Prediction vs known trajectory model

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 1086 | 5.723 | 6.515 | 6.091 | 6.355 | 1.322 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Real trajectory consistency vs known model

| count | mean error [m] | max error [m] |
| ---: | ---: | ---: |
| 10718 | 5.693 | 11.102 |

## Worst proposed predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 193.152 | 26 | 28.884 | 32.478 | 56.798 | 56.798 | 25.330 |
| 2 | 193.126 | 26 | 27.297 | 30.757 | 53.966 | 53.966 | 24.186 |
| 3 | 193.259 | 26 | 6.466 | 6.799 | 10.237 | 10.237 | 3.565 |
| 4 | 193.596 | 26 | 4.916 | 6.129 | 11.960 | 11.960 | 6.353 |
| 5 | 193.434 | 26 | 4.765 | 6.048 | 12.058 | 12.058 | 6.600 |

## Worst baseline predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| - | - | - | - | - | - | - | - |

> Note: all metrics and plots are computed only on the circular phase of the trajectory.

## RViz topics

- predicted trajectory: `/target/predicted_trajectory`

## Artifacts

- JSON summary: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_193336/prediction_eval.json`
- Plot PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_193336/prediction_eval_plot.png`
- XY comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_193336/prediction_eval_xy.png`
- Per-sample CSV: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_193336/prediction_eval_samples.csv`
