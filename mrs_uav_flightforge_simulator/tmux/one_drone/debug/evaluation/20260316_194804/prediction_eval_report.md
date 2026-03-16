# Prediction evaluation report

## Prediction vs ground truth

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 874 | 0.589 | 0.830 | 1.209 | 1.210 | 0.724 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Prediction vs known trajectory model

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 874 | 5.658 | 6.158 | 6.053 | 6.169 | 0.724 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Real trajectory consistency vs known model

| count | mean error [m] | max error [m] |
| ---: | ---: | ---: |
| 7207 | 5.373 | 8.177 |

## Worst proposed predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 77.788 | 26 | 4.674 | 5.050 | 8.201 | 8.201 | 3.250 |
| 2 | 75.000 | 26 | 4.144 | 4.564 | 7.737 | 7.737 | 3.283 |
| 3 | 58.919 | 26 | 3.685 | 4.055 | 6.852 | 6.852 | 2.901 |
| 4 | 96.020 | 26 | 3.308 | 3.601 | 5.964 | 5.964 | 2.445 |
| 5 | 92.970 | 26 | 3.188 | 3.489 | 5.853 | 5.853 | 2.445 |

## Worst baseline predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| - | - | - | - | - | - | - | - |

> Note: all metrics and plots are computed only on the circular phase of the trajectory.

## RViz topics

- predicted trajectory: `/target/predicted_trajectory`

## Artifacts

- JSON summary: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_194804/prediction_eval.json`
- Plot PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_194804/prediction_eval_plot.png`
- XY comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_194804/prediction_eval_xy.png`
- Per-sample CSV: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_194804/prediction_eval_samples.csv`
