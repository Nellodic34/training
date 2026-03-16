# Prediction evaluation report

## Prediction vs ground truth

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 685 | 0.499 | 0.750 | 1.049 | 1.050 | 0.694 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Prediction vs known trajectory model

| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| proposed | 684 | 6.093 | 6.810 | 6.302 | 6.682 | 0.695 |
| baseline | 0 | n/a | n/a | n/a | n/a | n/a |

## Real trajectory consistency vs known model

| count | mean error [m] | max error [m] |
| ---: | ---: | ---: |
| 5289 | 5.787 | 10.792 |

## Worst proposed predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 83.539 | 26 | 4.203 | 4.543 | 7.386 | 7.386 | 2.945 |
| 2 | 85.753 | 26 | 2.767 | 3.030 | 5.059 | 5.059 | 2.109 |
| 3 | 103.329 | 26 | 2.745 | 2.970 | 4.835 | 4.835 | 1.941 |
| 4 | 83.992 | 26 | 2.663 | 2.837 | 4.476 | 4.476 | 1.700 |
| 5 | 83.001 | 26 | 2.174 | 2.400 | 4.096 | 4.096 | 1.770 |

## Worst baseline predictions by ADE (vs GT)

| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| - | - | - | - | - | - | - | - |

> Note: all metrics and plots are computed only on the circular phase of the trajectory.

## RViz topics

- predicted trajectory: `/target/predicted_trajectory`

## Artifacts

- JSON summary: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_195823/prediction_eval.json`
- Plot PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_195823/prediction_eval_plot.png`
- XY comparison PNG: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_195823/prediction_eval_xy.png`
- Per-sample CSV: `/home/nello/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/debug/evaluation/20260316_195823/prediction_eval_samples.csv`
