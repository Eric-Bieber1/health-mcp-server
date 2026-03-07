"""Cronometer nutrition tools — 6 DB-only tools for nutrition data."""

from mcp_instance import mcp
from db import query_all, query_one

RDA = {
    "vitamin_d_iu": {"target": 600, "unit": "IU", "label": "Vitamin D"},
    "vitamin_c_mg": {"target": 90, "unit": "mg", "label": "Vitamin C"},
    "vitamin_a_iu": {"target": 3000, "unit": "IU", "label": "Vitamin A"},
    "vitamin_e_mg": {"target": 15, "unit": "mg", "label": "Vitamin E"},
    "vitamin_k_ug": {"target": 120, "unit": "µg", "label": "Vitamin K"},
    "calcium_mg": {"target": 1000, "unit": "mg", "label": "Calcium"},
    "iron_mg": {"target": 8, "unit": "mg", "label": "Iron"},
    "magnesium_mg": {"target": 420, "unit": "mg", "label": "Magnesium"},
    "zinc_mg": {"target": 11, "unit": "mg", "label": "Zinc"},
    "potassium_mg": {"target": 3400, "unit": "mg", "label": "Potassium"},
    "sodium_mg": {"target": 2300, "unit": "mg", "label": "Sodium"},
    "phosphorus_mg": {"target": 700, "unit": "mg", "label": "Phosphorus"},
    "selenium_ug": {"target": 55, "unit": "µg", "label": "Selenium"},
    "copper_mg": {"target": 0.9, "unit": "mg", "label": "Copper"},
    "manganese_mg": {"target": 2.3, "unit": "mg", "label": "Manganese"},
    "b1_mg": {"target": 1.2, "unit": "mg", "label": "B1 (Thiamine)"},
    "b2_mg": {"target": 1.3, "unit": "mg", "label": "B2 (Riboflavin)"},
    "b3_mg": {"target": 16, "unit": "mg", "label": "B3 (Niacin)"},
    "b5_mg": {"target": 5, "unit": "mg", "label": "B5 (Pantothenic)"},
    "b6_mg": {"target": 1.3, "unit": "mg", "label": "B6"},
    "b12_ug": {"target": 2.4, "unit": "µg", "label": "B12"},
    "folate_ug": {"target": 400, "unit": "µg", "label": "Folate"},
    "fiber_g": {"target": 38, "unit": "g", "label": "Fiber"},
    "omega3_g": {"target": 1.6, "unit": "g", "label": "Omega-3"},
    "cholesterol_mg": {"target": 300, "unit": "mg", "label": "Cholesterol"},
}


@mcp.tool()
def get_nutrition_daily(date: str) -> str:
    """Get daily macros, fat breakdown, and targets for a specific date.

    Args:
        date: Date in YYYY-MM-DD format.

    Returns calories, protein, carbs, fat, fiber, sugar, sodium, water,
    fat breakdown (saturated, mono, poly, trans, cholesterol, omega-3/6),
    and personal targets.
    (Source: database)
    """
    row = query_one("SELECT * FROM cronometer_daily WHERE date = ?", (date,))

    if not row:
        return f"No nutrition data found for {date}."

    def v(key, fmt=".1f", suffix=""):
        val = row.get(key)
        if val is None:
            return "N/A"
        return f"{val:{fmt}}{suffix}"

    cal_target = row.get("calorie_target")
    cal_actual = row.get("calories", 0) or 0
    cal_pct = f" ({cal_actual / cal_target * 100:.0f}%)" if cal_target else ""

    lines = [
        f"Nutrition — {date}",
        "=" * 45,
        "",
        "Macros:",
        f"  Calories:  {v('calories', ',.0f')}{cal_pct}",
        f"  Protein:   {v('protein_g')} g",
        f"  Carbs:     {v('carbs_g')} g  (Net: {v('net_carbs_g')} g)",
        f"  Fat:       {v('fat_g')} g",
        f"  Fiber:     {v('fiber_g')} g",
        f"  Sugar:     {v('sugars_g')} g  (Added: {v('added_sugars_g')} g)",
        f"  Sodium:    {v('sodium_mg', ',.0f')} mg",
        f"  Water:     {v('water_g', ',.0f')} g",
        "",
        "Fat Breakdown:",
        f"  Saturated:      {v('saturated_g')} g",
        f"  Monounsaturated:{v('monounsaturated_g')} g",
        f"  Polyunsaturated:{v('polyunsaturated_g')} g",
        f"  Trans Fat:      {v('trans_fat_g')} g",
        f"  Cholesterol:    {v('cholesterol_mg', ',.0f')} mg",
        f"  Omega-3:        {v('omega3_g')} g",
        f"  Omega-6:        {v('omega6_g')} g",
    ]

    if cal_target or row.get("protein_target_g"):
        lines.append("")
        lines.append("Targets:")
        if cal_target:
            lines.append(f"  Calories:  {cal_target:,.0f}")
        if row.get("protein_target_g"):
            lines.append(f"  Protein:   {row['protein_target_g']:.0f} g")
        if row.get("carbs_target_g"):
            lines.append(f"  Carbs:     {row['carbs_target_g']:.0f} g")
        if row.get("fat_target_g"):
            lines.append(f"  Fat:       {row['fat_target_g']:.0f} g")

    lines.append("")
    lines.append("(Source: database)")
    return "\n".join(lines)


@mcp.tool()
def get_nutrition_micros(date: str) -> str:
    """Get micronutrient intake for a specific date compared to RDA targets.

    Args:
        date: Date in YYYY-MM-DD format.

    Returns all 25 RDA-tracked nutrients with actual value, target, unit,
    and percentage of RDA — sorted by worst gaps first.
    (Source: database)
    """
    row = query_one("SELECT * FROM cronometer_daily WHERE date = ?", (date,))

    if not row:
        return f"No nutrition data found for {date}."

    entries = []
    for col, info in RDA.items():
        actual = row.get(col)
        if actual is None:
            actual = 0.0
        pct = (actual / info["target"] * 100) if info["target"] > 0 else 0
        entries.append((info["label"], actual, info["target"], info["unit"], pct))

    entries.sort(key=lambda e: e[4])

    lines = [
        f"Micronutrients — {date}",
        "=" * 60,
        f"{'Nutrient':<20} {'Actual':>8} {'Target':>8} {'Unit':<4} {'% RDA':>7}",
        "-" * 60,
    ]

    for label, actual, target, unit, pct in entries:
        flag = " *" if pct < 50 else ""
        lines.append(f"{label:<20} {actual:>8.1f} {target:>8.1f} {unit:<4} {pct:>6.0f}%{flag}")

    lines.append("")
    lines.append("* = below 50% of RDA")
    lines.append("(Source: database)")
    return "\n".join(lines)


@mcp.tool()
def get_nutrition_averages(days: int = 7) -> str:
    """Get average macro intake over the last N days.

    Args:
        days: Number of days to average over (1-90, default 7).

    Returns average calories, protein, carbs, fat, fiber vs targets,
    and the count of days with tracked data.
    (Source: database)
    """
    days = max(1, min(90, days))
    rows = query_all(
        "SELECT calories, protein_g, carbs_g, fat_g, fiber_g, "
        "calorie_target, protein_target_g, carbs_target_g, fat_target_g "
        "FROM cronometer_daily "
        "WHERE date >= date('now', ? || ' days') AND calories > 0 "
        "ORDER BY date DESC",
        (f"-{days}",),
    )

    if not rows:
        return f"No nutrition data found in the last {days} days."

    count = len(rows)

    def avg(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0

    avg_cal = avg("calories")
    avg_pro = avg("protein_g")
    avg_carb = avg("carbs_g")
    avg_fat = avg("fat_g")
    avg_fib = avg("fiber_g")

    cal_target = avg("calorie_target")
    pro_target = avg("protein_target_g")
    carb_target = avg("carbs_target_g")
    fat_target = avg("fat_target_g")

    def pct(actual, target):
        if target > 0:
            return f" ({actual / target * 100:.0f}%)"
        return ""

    lines = [
        f"Nutrition Averages — Last {days} Days ({count} days tracked)",
        "=" * 50,
        "",
        f"  Calories:  {avg_cal:,.0f}{pct(avg_cal, cal_target)}",
        f"  Protein:   {avg_pro:.1f} g{pct(avg_pro, pro_target)}",
        f"  Carbs:     {avg_carb:.1f} g{pct(avg_carb, carb_target)}",
        f"  Fat:       {avg_fat:.1f} g{pct(avg_fat, fat_target)}",
        f"  Fiber:     {avg_fib:.1f} g",
    ]

    if cal_target > 0:
        lines.append("")
        lines.append("Targets (daily):")
        lines.append(f"  Calories:  {cal_target:,.0f}")
        if pro_target > 0:
            lines.append(f"  Protein:   {pro_target:.0f} g")
        if carb_target > 0:
            lines.append(f"  Carbs:     {carb_target:.0f} g")
        if fat_target > 0:
            lines.append(f"  Fat:       {fat_target:.0f} g")

    lines.append("")
    lines.append("(Source: database)")
    return "\n".join(lines)


@mcp.tool()
def get_micro_averages(days: int = 7) -> str:
    """Get average micronutrient intake over the last N days compared to RDA.

    Args:
        days: Number of days to average over (1-90, default 7).

    Returns average for each of 25 RDA-tracked nutrients with percentage
    of RDA, sorted by worst gaps first.
    (Source: database)
    """
    days = max(1, min(90, days))
    cols = ", ".join(RDA.keys())
    rows = query_all(
        f"SELECT {cols} FROM cronometer_daily "
        "WHERE date >= date('now', ? || ' days') AND calories > 0",
        (f"-{days}",),
    )

    if not rows:
        return f"No nutrition data found in the last {days} days."

    count = len(rows)
    entries = []
    for col, info in RDA.items():
        vals = [r[col] for r in rows if r.get(col) is not None]
        avg_val = sum(vals) / len(vals) if vals else 0
        pct = (avg_val / info["target"] * 100) if info["target"] > 0 else 0
        entries.append((info["label"], avg_val, info["target"], info["unit"], pct))

    entries.sort(key=lambda e: e[4])

    lines = [
        f"Micronutrient Averages — Last {days} Days ({count} days tracked)",
        "=" * 60,
        f"{'Nutrient':<20} {'Avg':>8} {'Target':>8} {'Unit':<4} {'% RDA':>7}",
        "-" * 60,
    ]

    for label, avg_val, target, unit, pct in entries:
        flag = " *" if pct < 50 else ""
        lines.append(f"{label:<20} {avg_val:>8.1f} {target:>8.1f} {unit:<4} {pct:>6.0f}%{flag}")

    lines.append("")
    lines.append("* = below 50% of RDA")
    lines.append("(Source: database)")
    return "\n".join(lines)


@mcp.tool()
def get_meals(date: str) -> str:
    """Get all foods eaten on a specific date, grouped by meal.

    Args:
        date: Date in YYYY-MM-DD format.

    Returns foods grouped by meal (Breakfast, Lunch, Dinner, Snack)
    with calories, protein, carbs, and fat per food.
    (Source: database)
    """
    rows = query_all(
        "SELECT food_name, meal_group, calories, protein_g, carbs_g, fat_g, amount, unit "
        "FROM cronometer_servings WHERE date = ? ORDER BY meal_group, food_name",
        (date,),
    )

    if not rows:
        return f"No meal data found for {date}."

    meals: dict[str, list] = {}
    for r in rows:
        group = r.get("meal_group") or "Other"
        meals.setdefault(group, []).append(r)

    meal_order = ["Breakfast", "Lunch", "Dinner", "Snack", "Other"]

    lines = [
        f"Meals — {date}",
        "=" * 60,
    ]

    total_cal = 0
    for group in meal_order:
        foods = meals.get(group)
        if not foods:
            continue

        meal_cal = sum(f.get("calories", 0) or 0 for f in foods)
        total_cal += meal_cal
        lines.append("")
        lines.append(f"  {group} ({meal_cal:.0f} cal)")
        lines.append(f"  {'-' * 50}")

        for f in foods:
            name = f.get("food_name", "Unknown")
            cal = f.get("calories", 0) or 0
            pro = f.get("protein_g", 0) or 0
            carb = f.get("carbs_g", 0) or 0
            fat = f.get("fat_g", 0) or 0
            amt = f.get("amount", "")
            unit = f.get("unit", "")
            qty = f" ({amt} {unit})" if amt else ""
            lines.append(f"    {name}{qty}")
            lines.append(f"      {cal:.0f} cal | P: {pro:.1f}g | C: {carb:.1f}g | F: {fat:.1f}g")

    lines.append("")
    lines.append(f"  Total: {total_cal:,.0f} cal")
    lines.append("(Source: database)")
    return "\n".join(lines)


@mcp.tool()
def get_top_foods(days: int = 30) -> str:
    """Get most frequently eaten foods over the last N days.

    Args:
        days: Number of days to look back (1-90, default 30).

    Returns top 20 foods sorted by frequency, with average calories
    and macros per serving.
    (Source: database)
    """
    days = max(1, min(90, days))
    rows = query_all(
        "SELECT food_name, COUNT(*) as freq, "
        "AVG(calories) as avg_cal, AVG(protein_g) as avg_pro, "
        "AVG(carbs_g) as avg_carb, AVG(fat_g) as avg_fat "
        "FROM cronometer_servings "
        "WHERE date >= date('now', ? || ' days') "
        "GROUP BY food_name ORDER BY freq DESC LIMIT 20",
        (f"-{days}",),
    )

    if not rows:
        return f"No food data found in the last {days} days."

    lines = [
        f"Top Foods — Last {days} Days",
        "=" * 65,
        f"{'Food':<30} {'Freq':>5} {'Avg Cal':>8} {'P':>5} {'C':>5} {'F':>5}",
        "-" * 65,
    ]

    for r in rows:
        name = (r["food_name"] or "Unknown")[:29]
        freq = r["freq"]
        cal = r.get("avg_cal", 0) or 0
        pro = r.get("avg_pro", 0) or 0
        carb = r.get("avg_carb", 0) or 0
        fat = r.get("avg_fat", 0) or 0
        lines.append(f"{name:<30} {freq:>5} {cal:>7.0f} {pro:>5.1f} {carb:>5.1f} {fat:>5.1f}")

    lines.append("")
    lines.append("(Source: database)")
    return "\n".join(lines)
