def evaluate_policy(office_days, total_hours):
    violations = []

    if office_days < 3:
        violations.append("Fewer than 3 office days")

    if total_hours < 15:
        violations.append("Fewer than 15 office hours")

    return {
        "compliant": len(violations) == 0,
        "violations": violations,
    }
