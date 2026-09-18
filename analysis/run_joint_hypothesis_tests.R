#!/usr/bin/env Rscript

# Joint hypothesis tests for the five tariff-event mediation scenarios.
#
# This is a standalone extraction of the preprocessing, SCAD/LLA selection,
# HBIC tuning, post-selection refit, and OurMethod calculations in
# analysis/run_mediation_analysis.R from:
# https://github.com/qilankhong/sp500-tariff-mediation-2025
#
# Usage:
#   Rscript run_joint_hypothesis_tests.R \
#     sp500_analysis_data.csv event_returns.csv joint_hypothesis_tests.csv
#
# Arguments are optional. Defaults match the repository's data locations and
# write joint_hypothesis_tests_S1-S5.csv in the current directory.

suppressPackageStartupMessages(library(glmnet))

args <- commandArgs(trailingOnly = TRUE)
main_data_path <- if (length(args) >= 1) args[[1]] else
  "data/processed/sp500_analysis_data.csv"
event_returns_path <- if (length(args) >= 2) args[[2]] else
  "data/derived/event_returns.csv"
output_path <- if (length(args) >= 3) args[[3]] else
  "joint_hypothesis_tests_S1-S5.csv"

events <- c(
  "S1_Decline",
  "S2_Escalation_Collapse",
  "S3_Policy_Shock_Jump",
  "S4_Uncertainty_Decline",
  "S5_Long_Term_Adjustment"
)

sector_cols_all <- c(
  "Basic.Materials", "Communication.Services", "Consumer.Cyclical",
  "Consumer.Defensive", "Energy", "Financial.Services", "Healthcare",
  "Industrials", "Real.Estate", "Technology", "Utilities"
)

if (!file.exists(main_data_path)) stop("Main data file not found: ", main_data_path)
if (!file.exists(event_returns_path)) stop("Event-return file not found: ", event_returns_path)

# check.names=TRUE reproduces read.csv() in the repository: spaces and colons
# in source headers become syntactically valid names (e.g. Basic.Materials).
all_data <- read.csv(main_data_path, header = TRUE)
event_returns <- read.csv(event_returns_path)
all_data <- merge(all_data, event_returns, by = "symbol", all.x = TRUE)

stopifnot(all(events %in% colnames(all_data)))
stopifnot(all(sector_cols_all %in% colnames(all_data)))

# Utilities remains the omitted sector, exactly as in the repository.
sector_cols <- setdiff(sector_cols_all, "Utilities")
X <- data.matrix(all_data[, sector_cols, drop = FALSE])
X <- cbind(Intercept = rep(1, nrow(X)), X)
X[is.na(X)] <- 0

# The repository recognizes financial-statement mediators by these prefixes.
mediator_cols <- grep("^(IS|BS|CF)\\.", colnames(all_data), value = TRUE)
mediator_frame <- all_data[, mediator_cols, drop = FALSE]
mediator_sd <- vapply(mediator_frame, sd, numeric(1), na.rm = TRUE)
valid_mediator <- is.finite(mediator_sd) & mediator_sd > 0
if (any(!valid_mediator)) {
  message("Dropping ", sum(!valid_mediator),
          " all-missing or zero-variance mediator(s).")
}
mediator_cols <- mediator_cols[valid_mediator]
M <- data.matrix(scale(mediator_frame[, valid_mediator, drop = FALSE]))
M[is.na(M)] <- 0

# The following routines reproduce the repository implementation. In
# particular, the lambda grid, SCAD constant, HBIC expression, and tie-breaking
# rule are unchanged.
deSCAD <- function(z, lamb, a = 3.7) {
  1 * (z <= lamb) + pmax((a * lamb - z), 0) / ((a - 1) * lamb) * (lamb < z)
}

ZouAlgo_h1 <- function(X, Y, M, w, lamb) {
  n <- nrow(X)
  p <- ncol(M)
  q <- ncol(X)
  alpha_int <- matrix(NA_real_, ncol = 1, nrow = p + q)
  U <- which(w == 0)
  V <- which(w != 0)
  Xt <- sqrt(2) * cbind(M, X)
  Xts <- Xt
  for (j in seq_along(V)) Xts[, V[j]] <- Xt[, V[j]] * lamb / w[V[j]]
  Xus <- as.matrix(Xts[, U, drop = FALSE])
  Xvs <- as.matrix(Xts[, V, drop = FALSE])
  Pu <- Xus %*% solve(crossprod(Xus)) %*% t(Xus)
  Qu <- diag(n) - Pu
  Ys <- sqrt(2) * Y
  Yss1 <- sqrt(2) * Qu %*% Y
  Xvss1 <- Qu %*% Xvs
  reg1 <- glmnet(Xvss1, Yss1, family = "gaussian", alpha = 1, lambda = lamb)
  Betavs <- matrix(reg1$beta, ncol = 1)
  Betaus <- solve(crossprod(Xus)) %*% crossprod(Xus, Ys - Xvs %*% Betavs)
  alpha_int[U] <- Betaus
  alpha_int[V] <- Betavs * lamb / w[V]
  alpha_int
}

ZouMethod_h1 <- function(X, Y, M, lamb) {
  p <- ncol(M)
  q <- ncol(X)
  w1 <- matrix(0, nrow = p + q, ncol = 1)
  w1[seq_len(p)] <- 1
  w1[p + q] <- 0
  alpha_int <- ZouAlgo_h1(X, Y, M, w1, lamb)
  w2 <- matrix(0, nrow = p + q, ncol = 1)
  for (j in seq_len(p)) w2[j] <- deSCAD(alpha_int[j], lamb)
  ZouAlgo_h1(X, Y, M, w2, lamb)
}

HBIC_Zou <- function(X, Y, M, lamb) {
  n <- nrow(X)
  p <- ncol(M)
  q <- ncol(X)
  result <- ZouMethod_h1(X, Y, M, lamb)
  alpha0 <- result[seq_len(p)]
  alpha1 <- result[(p + 1):(p + q)]
  df <- sum(abs(alpha0) > 0) + q
  residual <- Y - M %*% alpha0 - X %*% alpha1
  sigma_hat <- as.numeric(crossprod(residual) / n)
  bic <- log(sigma_hat) + df * log(log(n)) * log(p + q) / n
  list(BIC = bic, alpha0 = alpha0, alpha1 = alpha1)
}

OurMethod <- function(X, Y, M, alpha0_hat, alpha1_hat, alpha0_tld,
                      gamma_hat, invXX) {
  n <- nrow(X)
  q <- ncol(X)
  residual_alt <- Y - M %*% alpha0_hat - X %*% alpha1_hat
  residual_null <- Y - M %*% alpha0_tld
  RSS12 <- crossprod(residual_alt)
  RSS02 <- crossprod(residual_null)
  sigma_total <- crossprod(Y - X %*% gamma_hat) / (n - q)

  s <- sum(alpha0_hat != 0)
  df <- s + q
  sigma1_hat <- as.numeric(RSS12 / (n - df))
  sigma2_hat <- as.numeric(pmax(0, sigma_total - sigma1_hat))
  beta_hat <- gamma_hat - alpha1_hat

  Sigma_MX <- crossprod(M, X) / n
  Sigma_MM <- crossprod(M) / n
  B <- invXX %*% t(Sigma_MX) %*%
    solve(Sigma_MM - Sigma_MX %*% invXX %*% t(Sigma_MX)) %*%
    Sigma_MX %*% invXX
  cov_beta_hat <- sigma2_hat * invXX + sigma1_hat * B

  # These are the repository's three statistics, unchanged.
  Sn <- as.numeric(n * t(beta_hat) %*% solve(cov_beta_hat) %*% beta_hat)
  Tn1 <- as.numeric((n - df) * (RSS02 - RSS12) / RSS12)
  Tn2 <- as.numeric(n * log(RSS02 / RSS12))

  list(Sn = Sn, Tn1 = Tn1, Tn2 = Tn2, selected = s, residual_df = n - df)
}

run_event <- function(event_name) {
  message("Running ", event_name, " ...")
  y_original <- all_data[[event_name]]
  Y <- data.matrix(scale(y_original))
  Y[is.na(Y)] <- 0

  n <- nrow(M)
  p <- ncol(M)
  q <- ncol(X)
  lambda_grid <- seq(0.1, 0.114, length.out = 20)
  hbic <- numeric(length(lambda_grid))
  alpha0_record <- matrix(NA_real_, nrow = length(lambda_grid), ncol = p)
  alpha1_record <- matrix(NA_real_, nrow = length(lambda_grid), ncol = q)

  for (ii in seq_along(lambda_grid)) {
    result <- HBIC_Zou(X, Y, M, lambda_grid[ii])
    hbic[ii] <- result$BIC
    alpha0_record[ii, ] <- result$alpha0
    alpha1_record[ii, ] <- result$alpha1
  }

  # Repository rule: if HBIC ties, take the last minimizing lambda.
  id <- tail(which(hbic == min(hbic)), 1)
  alpha0_selected <- alpha0_record[id, ]
  active <- which(alpha0_selected != 0)
  if (length(active) == 0) stop(event_name, ": no mediator selected; refit undefined")
  M_A <- M[, active, drop = FALSE]

  # Repository post-selection OLS refit under H1 and selected-mediator-only OLS
  # fit under H0. This preserves its actual OurMethod inputs.
  Z <- cbind(M_A, X)
  alpha_refit <- solve(crossprod(Z)) %*% crossprod(Z, Y)
  s <- ncol(M_A)
  alpha0_hat <- alpha_refit[seq_len(s)]
  alpha1_hat <- alpha_refit[(s + 1):(s + q)]
  alpha0_tld <- solve(crossprod(M_A)) %*% crossprod(M_A, Y)
  gamma_hat <- solve(crossprod(X)) %*% crossprod(X, Y)
  invXX <- solve(crossprod(X) / n)

  test <- OurMethod(X, Y, M_A, alpha0_hat, alpha1_hat, alpha0_tld,
                    gamma_hat, invXX)

  # Guo et al. (2023), Sections 2.3-2.4:
  #   Sn  -> chi-square(q) under H0: beta = 0.
  #   Tn  -> chi-square(q) under H0: alpha1 = 0.
  # Tn1 is the repository's direct-effect statistic and is reported as primary.
  # Tn2 is an additional LRT-style statistic found in the code but not the
  # paper's displayed F-type statistic; chi-square(q) is a sensitivity
  # calibration. The classical post-selection F calibration is also supplied:
  # Tn1/q compared with F(q, n-s-q). It is descriptive because selection makes
  # an exact finite-sample F claim inappropriate.
  data.frame(
    Scenario = event_name,
    Sample_Size_N = n,
    Joint_Test_DF_Q = q,
    Joint_Test_Coefficients =
      "Intercept (Utilities baseline) + 10 non-Utilities sector indicators",
    Selected_Mediators = test$selected,
    Lambda = lambda_grid[id],
    Residual_DF = test$residual_df,
    Wald_Sn = test$Sn,
    Wald_ChiSq_DF_Q = q,
    Wald_P_ChiSq = pchisq(test$Sn, df = q, lower.tail = FALSE),
    Direct_Tn1_FType = test$Tn1,
    Direct_Tn1_ChiSq_DF_Q = q,
    Direct_Tn1_P_ChiSq = pchisq(test$Tn1, df = q, lower.tail = FALSE),
    Direct_Tn1_Classical_F = test$Tn1 / q,
    Direct_Tn1_F_DF1 = q,
    Direct_Tn1_F_DF2 = test$residual_df,
    Direct_Tn1_P_F_Descriptive = pf(test$Tn1 / q, q, test$residual_df,
                                    lower.tail = FALSE),
    Direct_Tn2_LRTStyle = test$Tn2,
    Direct_Tn2_ChiSq_DF_Q = q,
    Direct_Tn2_P_ChiSq_Sensitivity = pchisq(test$Tn2, df = q,
                                            lower.tail = FALSE),
    stringsAsFactors = FALSE
  )
}

summary_table <- do.call(rbind, lapply(events, run_event))
output_dir <- dirname(output_path)
if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)
write.csv(summary_table, output_path, row.names = FALSE)

message("Wrote: ", normalizePath(output_path, mustWork = FALSE))
print(summary_table, row.names = FALSE, digits = 6)
