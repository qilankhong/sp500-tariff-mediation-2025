# Sparse generalized mediation analysis for the five tariff-event outcomes.
library(glmnet)
library(dplyr)

args <- commandArgs(trailingOnly = TRUE)
main_data_path <- if (length(args) >= 1) args[[1]] else "data/processed/sp500_analysis_data.csv"
event_returns_path <- if (length(args) >= 2) args[[2]] else "data/derived/event_returns.csv"
requested_event <- if (length(args) >= 3) args[[3]] else "S1_Decline"

all_data <- read.csv(
  main_data_path,
  header = TRUE
)
event_returns <- read.csv(event_returns_path)

# Merge event returns into main dataset by firm symbol
all_data <- merge(
  all_data,
  event_returns,
  by = "symbol",
  all.x = TRUE
)

# all_data will look like this:
# symbol
# [sector dummies]
# [~250 mediator columns]
# S1_Decline
# S2_Escalation_Collapse
# S3_Policy_Shock_Jump
# S4_Uncertainty_Decline
# S5_Long_Term_Adjustment

# Event window is supplied as the third command-line argument.
EVENT_Y <- requested_event

event_tag <- EVENT_Y
stopifnot(EVENT_Y %in% colnames(all_data))

y_original <- all_data[[EVENT_Y]]
Y <- data.matrix(scale(y_original))

sector_cols_all <- c(
  "Basic.Materials", "Communication.Services", "Consumer.Cyclical",
  "Consumer.Defensive", "Energy", "Financial.Services", "Healthcare",
  "Industrials", "Real.Estate", "Technology", "Utilities"
)
stopifnot(all(sector_cols_all %in% colnames(all_data)))
sector_cols <- setdiff(sector_cols_all, "Utilities")
X = data.matrix(all_data[, sector_cols])   # Utilities is the baseline sector
X = cbind(rep(1, nrow(X)), X)
colnames(X)[1] = "Intercept"
colnames(X)[1] = "Intercept"

# Identify mediator columns = everything AFTER sectors, EXCLUDING event Y's
event_Y_cols <- c(
  "S1_Decline",
  "S2_Escalation_Collapse",
  "S3_Policy_Shock_Jump",
  "S4_Uncertainty_Decline",
  "S5_Long_Term_Adjustment"
)

mediator_cols <- grep("^(IS|BS|CF)\\.", colnames(all_data), value = TRUE)
mediator_frame <- all_data[, mediator_cols, drop = FALSE]
mediator_sd <- vapply(
  mediator_frame,
  function(values) sd(values, na.rm = TRUE),
  numeric(1)
)
valid_mediator <- is.finite(mediator_sd) & mediator_sd > 0
dropped_mediators <- mediator_cols[!valid_mediator]
if (length(dropped_mediators) > 0) {
  cat("Dropped all-missing or zero-variance mediators:\n  ",
      paste(dropped_mediators, collapse = "\n  "), "\n")
}
mediator_cols <- mediator_cols[valid_mediator]
M <- data.matrix(scale(mediator_frame[, valid_mediator, drop = FALSE]))

X[is.na(X)] <- 0
Y <- scale(y_original)
Y[is.na(Y)] <- 0
Y <- data.matrix(Y)
M[is.na(M)] <- 0

cat("✅ Dimensions confirmed:\n",
    "Y:", dim(Y), "\nX:", dim(X), "\nM:", dim(M), "\n")

# --------- DID NOT TOUCH ANYTHING UNDER HERE ---------- #
deSCAD <- function(z,lamb,a=3.7){
  return(1*(z<=lamb)+pmax((a*lamb-z),0)/((a-1)*lamb)*(lamb<z))
}

ZouAlgo_h1 <- function(X,Y,M,w,lamb){
  n = nrow(X)
  p = ncol(M)
  q = ncol(X)
  alpha_int = matrix(NA,ncol=1,nrow=(p+q))

  U = which(w == 0)
  V = which(w!=0)
  Xt = sqrt(2)*cbind(M,X)
  Xts = Xt
  for(j in 1:length(V)){
    Xts[,V[j]] = Xt[,V[j]] * lamb/w[V[j]]
  }

  Xus = as.matrix(Xts[,U])
  Xvs = as.matrix(Xts[,V])
  Pu = Xus%*%solve(t(Xus)%*%Xus)%*%t(Xus)
  Qu = diag(n) - Pu
  Ys = sqrt(2)*Y
  Yss1 = sqrt(2)*Qu%*%Y
  Xvss1 = Qu%*%Xvs
  reg1 = glmnet(Xvss1,Yss1,family = "gaussian",alpha=1,lambda=lamb)
  Betavs = matrix(reg1$beta,ncol=1)
  Betaus = solve(t(Xus)%*%Xus)%*%t(Xus)%*%(Ys - Xvs%*%Betavs)
  alpha_int[U] = Betaus
  alpha_int[V] = Betavs*lamb/w[V]
  return(alpha_int)
}

###############################################
## Two step sparsity Under H1: alpha1 != 0
###############################################
ZouMethod_h1<- function(X,Y,M,lamb){
  # Step 1 using Lasso
  w1 = matrix(0,nrow = (p+q),ncol=1)
  w1[1:p] = 1
  w1[p+q] = 0
  alpha_int = ZouAlgo_h1(X,Y,M,w1,lamb)
  #res1 = glmnet(as.matrix(cbind(M,X)),Y,family = "gaussian",alpha=1,lambda=lamb,penalty.factor = w1)
  #alpha_int = coef(res1)[-1]
  # Step 2 using linear approximation of SCAD
  w2 = matrix(0,nrow = (p+q),ncol=1)
  for(j in 1:p){
    w2[j] = deSCAD(alpha_int[j],lamb)
  }
  alpha = ZouAlgo_h1(X,Y,M,w2,lamb)
  #res2 = glmnet(as.matrix(cbind(M,X)),Y,family = "gaussian",alpha=1,lambda=lamb,penalty.factor = w2)
  return(alpha)
}

#########################
# Use HBIC to choose lambda
#########################
HBIC_Zou <- function(X,Y,M,lamb){
  n = nrow(X)
  p = ncol(M)
  q = ncol(X)
  result <- ZouMethod_h1(X,Y,M,lamb)
  alpha0 = result[1:p]
  alpha1 = result[(p+1):(p+q)]

  df = length(which(abs(alpha0)> 0))+q
  tmp = Y - M%*%alpha0 - X%*% alpha1
  sigma_hat = t(tmp)%*%tmp/n
  BIC = log(sigma_hat) + df*log(log(n))*log(p+q)/n
  #obj = objective(X,Y,M,alpha0,alpha1,lamb)
  return(list(BIC=BIC,alpha0=alpha0,alpha1 = alpha1))
}

OurMethod<-function(X,Y,M,alpha0_hat,alpha1_hat,alpha0_tld,gamma_hat,invXX){
  n = nrow(X)
  RSS12 = t(Y - M%*%alpha0_hat - X%*%alpha1_hat) %*% (Y - M%*%alpha0_hat - X%*%alpha1_hat) # Test direct effect
  RSS02 = t(Y - M%*% alpha0_tld) %*% (Y - M%*%alpha0_tld)
  RSS01 = t(Y - X%*%alpha1_hat) %*% (Y - X%*%alpha1_hat) # Test indirect effect
  RSS11 = t(Y-X%*%gamma_hat) %*% (Y-X%*%gamma_hat)

  A = which(alpha0_hat!=0)
  s = length(A)
  df = s+q
  sigma1_hat = as.numeric(RSS12/(n - df))
  sigmaT_hat = t(Y-X%*%gamma_hat) %*% (Y-X%*%gamma_hat)/(n-q)
  sigma2_hat = pmax(0,(sigmaT_hat - sigma1_hat))
  beta_hat = gamma_hat -alpha1_hat

  M_A = M[,A]
  tmp1 = cbind(t(X)%*%X,t(X)%*%M_A)
  tmp2 = cbind(t(M_A)%*%X,t(M_A)%*%M_A )
  Sigma_hat = rbind(tmp1,tmp2)/n
  Sigma_MX =t(M_A)%*%X/n
  Sigma_MM = t(M_A)%*%M_A /n

  B = invXX %*%t(Sigma_MX) %*%solve(Sigma_MM -  Sigma_MX%*%invXX %*% t(Sigma_MX)) %*%Sigma_MX %*%invXX
  var_alpha1_hat = sigma1_hat*(invXX + B)
  cov_beta_hat = sigma2_hat * invXX + sigma1_hat * B


  # Test for beta
  # Wald's test
  Sn = n*t(beta_hat) %*% solve(cov_beta_hat) %*% beta_hat
  # Test for alpha1
  # LRT
  Tn1 = (n-df) * (RSS02-RSS12)/RSS12
  Tn2 = n*log(RSS02/RSS12)
  return(list(Sn = Sn, Tn1 = Tn1, Tn2 = Tn2, beta_hat = beta_hat, B = B,
              var_beta = cov_beta_hat, var_alpha1_hat = var_alpha1_hat,
              alpha0_hat = alpha0_hat,alpha1_hat = alpha1_hat,
              alpha0_tld= alpha0_tld, sigma1_hat = sigma1_hat, sigma2_hat = sigma2_hat))
}

Refit<-function(X,Y,M_A,gamma_hat,invXX){
  s = ncol(M_A)
  M_A = M[,A]
  q = ncol(X)
  Z = cbind(M_A, X)
  alpha_hat_rf = solve(t(Z)%*%Z)%*%t(Z)%*%Y
  alpha0_hat_rf = alpha_hat_rf[1:s]
  alpha1_hat_rf = alpha_hat_rf[(s+1):(s+q)]
  print(length(alpha1_hat_rf))
  alpha0_tld_rf = solve(t(M_A)%*%M_A)%*%t(M_A)%*%Y

  return(OurMethod(X, Y,M_A,alpha0_hat_rf,alpha1_hat_rf,alpha0_tld_rf,gamma_hat,invXX))
}

n = nrow(M)
p = ncol(M)
q = ncol(X)
ngrid = 20
lamb_grid =  seq(0.1,0.114,length.out = ngrid)
gamma_hat = solve(t(X)%*%X)%*%t(X)%*%Y
Sigma_XX = t(X)%*%X/n
invXX = solve(Sigma_XX)
hbic= c() #matrix(NA, ncol = ngrid,nrow = length(rho2_grid))
alpha0_rcd = matrix(NA,nrow = ngrid,ncol=p)
alpha1_rcd = matrix(NA,nrow = ngrid,ncol=q)
for( ii in 1:ngrid){
  print(lamb_grid[ii])
  result = HBIC_Zou(X,Y,M,lamb_grid[ii])
  hbic[ii] = result$BIC
  alpha0_rcd[ii,]=result$alpha0
  alpha1_rcd[ii,]=result$alpha1
  print(colnames(M)[which(alpha0_rcd[ii,]!=0)])
  print("-------")
}

id = which(hbic==min(hbic))
id = tail(id,1)
lamb = lamb_grid[id]
# print("lambda= ", lamb)
alpha0_hat = alpha0_rcd[id,]
alpha1_hat = alpha1_rcd[id,]

A = which(alpha0_hat!=0)

M_A = M[,A]

rf <- Refit(X, Y, M_A, gamma_hat, invXX)
fit4 = summary(lm(Y~ 0+X+M_A))
fit4 = lm(y_original~ 0+X+M_A)
# Removed block because original block = four months, much longer
# gamma_hat = solve(t(X)%*%X)%*%t(X)%*%y_original
# rf <- Refit(X, y_original, M_A, gamma_hat, invXX)

# Generate Latex tables
ans = data.frame(e0 = rep('&',length(rf$alpha1_hat)),
                 direct=round(rf$alpha1_hat,digits = 4),
                 e1 = rep('&',length(rf$alpha1_hat)),
                 direct_std = round(sqrt(diag(rf$var_alpha1_hat)/n),digits = 4),
                 e2 = rep('&',length(rf$alpha1_hat)),
                 indirect = round(rf$beta_hat,digits = 4),
                 e3 = rep('&',length(rf$alpha1_hat)),
                 indirect_std = round(sqrt(diag(rf$var_beta)/n),digits = 4),
                 e4 = rep('\\',length(rf$alpha1_hat))
                 )

# one change here #
fit4 = summary(lm(y_original ~ 0 + X + M_A))
# end change#

ans2 = data.frame(e0 = rep('&',length(rf$alpha0_hat)),
                  effect = round(rf$alpha0_hat,digits = 4),
                  e0 = rep('&',length(rf$alpha0_hat)),
                  std = round(fit4$coefficients[12:nrow(fit4$coefficients),2],digits = 4),
                  e4 = rep('\\',length(rf$alpha0_hat)))

# ------ UNLESS EXPLICITLY NOTED, NO CHANGES ABOVE HERE ---- #

# Clean versions of the result tables ---------------------------

# 1. Direct & Indirect effects
direct_indirect_clean <- data.frame(
  Variable = colnames(X),
  Direct_Effect = round(rf$alpha1_hat, 4),
  Direct_SE = round(sqrt(diag(rf$var_alpha1_hat) / n), 4),
  Indirect_Effect = round(rf$beta_hat, 4),
  Indirect_SE = round(sqrt(diag(rf$var_beta) / n), 4)
)

# 2. Mediator effects
fit4 = summary(lm(y_original ~ 0 + X + M_A))
coef_table <- fit4$coefficients
mediator_rows <- grep("^M_A", rownames(coef_table))
mediator_clean <- data.frame(
  Mediator = colnames(M_A),
  Effect = round(rf$alpha0_hat, 4),
  Std_Error = round(coef_table[mediator_rows, 2], 4)
)

# 3. Save both as CSV files (downloads to working directory)
# ---- Auto timestamped file saving ----
timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")

#Creating new folder
run_dir <- file.path(
  "results",
  paste0(timestamp, "_", EVENT_Y)
)

if (!dir.exists(run_dir)) {
  dir.create(run_dir, recursive = TRUE)
}

cat("📁 Saving results to:", run_dir, "\n")

#

direct_file <- paste0(
  "Direct_Indirect_",
  EVENT_Y,
  "_",
  timestamp,
  ".csv"
)

write.csv(
  direct_indirect_clean,
  file.path(run_dir, direct_file),
  row.names = FALSE
)

mediator_file <- paste0(
  "Mediator_Effects_",
  EVENT_Y,
  "_",
  timestamp,
  ".csv"
)

write.csv(
  mediator_clean,
  file.path(run_dir, mediator_file),
  row.names = FALSE
)

cat(
  "✅ Files saved:\n",
  " -", direct_file, "\n",
  " -", mediator_file, "\n"
)

# -------------------------------------
