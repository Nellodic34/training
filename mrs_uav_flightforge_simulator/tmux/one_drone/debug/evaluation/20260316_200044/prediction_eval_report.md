# Prediction evaluation report

## Prediction vs ground truth

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 520 | 0.583 | 0.885 | 1.179 | 1.180 | 0.748 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Prediction vs known trajectory model

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 520 | 11.969 | 12.641 | 12.061 | 13.147 | 0.748 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Real trajectory consistency vs known model

| count | mean error [m] | max error [m] |
| ---: | ---: | ---: |
| 6551 | 11.828 | 18.418 |

## Worst proposed predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 173.991 | 26 | 5.459 | 5.933 | 9.765 | 9.765 | 3.958 |
| 2 | 211.404 | 26 | 4.555 | 4.960 | 8.213 | 8.213 | 3.353 |
| 3 | 175.001 | 26 | 3.956 | 4.259 | 6.897 | 6.897 | 2.703 |
| 4 | 197.852 | 26 | 3.814 | 4.265 | 7.047 | 7.047 | 3.197 |
| 5 | 213.478 | 26 | 3.798 | 4.183 | 7.075 | 7.075 | 2.995 |

## Worst baseline predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| - | - | - | - | - | - | - | - |

> Note: all metrics and plots are computed only on the circular phase of the trajectory.

## RViz topics

- predicted trajectory: `/target/predicted_trajectory`

## Artifacts

- JSON summary: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_200044/prediction_eval.json`
- Plot PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_200044/prediction_eval_plot.png`
- XY comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_200044/prediction_eval_xy.png`
- Per-sample CSV: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_200044/prediction_eval_samples.csv`
