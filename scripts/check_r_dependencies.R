required <- c("glmnet", "dplyr")
missing <- required[!vapply(required, requireNamespace, logical(1), quietly = TRUE)]

if (length(missing) > 0) {
  stop(
    "Missing R packages: ", paste(missing, collapse = ", "),
    ". Install with install.packages(c(",
    paste(sprintf('"%s"', missing), collapse = ", "), "))"
  )
}

cat("R dependencies are installed.\n")
invisible(parse(file = "analysis/run_mediation_analysis.R"))
cat("R analysis syntax is valid.\n")
