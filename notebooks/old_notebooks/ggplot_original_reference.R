library(ggplot2)
library(dplyr)
library(stringr)

# --- 1. Generate Data ---
get_random_data <- function(n = 10) {
  # Generates a random dataframe for plotting
  categories <- LETTERS[1:n]
  values <- sample(10:100, n, replace = TRUE)
  return(data.frame(Category = categories, Value = values))
}

generate_random_ggplot <- function() {

  # Generate Data (Random n between 5 and 12)
  df <- get_random_data(sample(5:12, 1))

  # --- 2. Determine Random Parameters ---

  # Rule: 74% Vertical, 26% Horizontal
  is_vertical <- runif(1) < 0.74

  # Rule: 61% have title
  has_title <- runif(1) < 0.61
  title_text <- NULL
  subtitle_text <- NULL

  # Theme element placeholders
  plot_title_element <- element_text()

  possible_titles <- c(
    "Sales Distribution 2024", "Regional Population Metrics", "Customer Satisfaction Scores",
    "Inventory Levels by Category", "Quarterly Revenue Growth", "Survey Response Analysis",
    "Average Temperature Data", "Product Performance Review", "Market Share Distribution",
    "Website Traffic Sources", "Employee Engagement Indices", "Monthly Expense Breakdown"
  )

  if (has_title) {
    base_title <- sample(possible_titles, 1)

    # Title Alignment
    # Anchor middle (hjust 0.5) 79%, start (hjust 0) 21%
    t_hjust <- if (runif(1) < 0.79) 0.5 else 0

    # Title Color
    if (runif(1) < 0.60) {
      t_color <- "black"
    } else {
      t_color <- sample(c('#555555', '#3f51b5', '#c62828'), 1)
    }

    # Title Size
    if (runif(1) < 0.80) {
      t_size <- sample(12:18, 1)
    } else {
      t_size <- sample(20:24, 1)
    }

    # 2% Chance of Subtitle
    if (runif(1) < 0.02) {
      title_text <- base_title
      subtitle_text <- "Detailed Overview & Analysis"
    } else {
      title_text <- base_title
    }

    plot_title_element <- element_text(
      hjust = t_hjust,
      color = t_color,
      size = t_size,
      face = "bold" # Ggplot titles look better bold usually, optional
    )
  }

  # Rule: 10% plot outline
  has_view_outline <- runif(1) < 0.10

  # Rule: Gridlines (52% Quant, 13% Both)
  # In Altair/Python logic:
  # If Vertical: Quant is Y axis. If Horizontal: Quant is X axis.
  r_grid <- runif(1)
  show_grid_x <- FALSE
  show_grid_y <- FALSE

  if (r_grid < 0.52) {
    if (is_vertical) show_grid_y <- TRUE else show_grid_x <- TRUE
  } else if (r_grid < 0.65) {
    show_grid_x <- TRUE
    show_grid_y <- TRUE
  }
  # Else both False

  # Rule: Axis Labels
  # X Axis Logic
  r_lx <- runif(1)
  x_angle <- 0
  show_x_labels <- TRUE

  if (r_lx < 0.92) { x_angle <- 0 }
  else if (r_lx < 0.96) { x_angle <- 315 } # -45 degrees in ggplot is often treated as 315 or 45 w/ hjust
  else if (r_lx < 0.97) { x_angle <- 270 } # -90 degrees
  else { show_x_labels <- FALSE }

  # Y Axis Logic
  r_ly <- runif(1)
  y_angle <- 0
  show_y_labels <- TRUE

  if (r_ly < 0.98) { y_angle <- 0 }
  else if (r_ly < 0.99) { y_angle <- 270 }
  else { show_y_labels <- FALSE }

  label_color <- "black"
  if (runif(1) < 0.15) {
    label_color <- sample(c('#666666', '#1f77b4', '#d62728'), 1)
  }

  # --- 3. Color Logic (50% Uniform / 50% Varied) ---
  is_uniform_color <- runif(1) < 0.50

  color_palette_hex <- c(
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    '#393b79', '#637939', '#8c6d31', '#843c39', 'black'
  )

  # Legend Logic
  has_legend <- runif(1) < 0.09
  legend_pos <- "none"
  legend_box_background <- element_blank()

  if (has_legend) {
    r_leg <- runif(1)
    if (r_leg < 0.33) legend_pos <- "right"
    else if (r_leg < 0.43) legend_pos <- "top"
    # ggplot doesn't have exact top-right/top-left keywords, using approximation or standard
    else if (r_leg < 0.76) legend_pos <- c(0.9, 0.9) # inside top right
    else if (r_leg < 0.86) legend_pos <- c(0.1, 0.9) # inside top left
    else if (r_leg < 0.96) legend_pos <- "bottom"
    else legend_pos <- "right"

    # Legend Border randomization
    if (runif(1) < 0.20) {
      legend_box_background <- element_rect(color = "black", fill = NA)
    }
  }

  # --- 4. Bar Styles ---
  # Rounded corners are excluded as requested.

  bar_stroke_color <- if (runif(1) < 0.27) "black" else NA
  bar_stroke_size <- if (!is.na(bar_stroke_color)) 0.5 else 0 # ggplot size is slightly different scale than altair

  bg_color <- "white"
  if (runif(1) < 0.03) bg_color <- "#f0f0f0"

  # --- 5. Construct Chart ---

  # Orientation Mapping
  if (is_vertical) {
    p <- ggplot(df, aes(x = Category, y = Value))
    # If vertical, X needs the angle rotation logic
    final_x_angle <- x_angle
    final_y_angle <- y_angle
  } else {
    p <- ggplot(df, aes(y = Category, x = Value))
    # If horizontal (coord_flip logic essentially), the "X" axis visually is Values
    # But in ggplot aes mapping y=Category, the Y axis text elements control Category labels.
    # To maintain the logic: The Category axis gets the rotation logic defined by x_angle/x_labels vars?
    # In the original script: x_axis_obj is always X('Category') if vertical, X('Value') if horizontal.
    # Let's map strict visual correspondence to the random vars generated:
    # If Vertical: Category is X (use x vars), Value is Y (use y vars).
    # If Horizontal: Value is X (use x vars), Category is Y (use y vars).
    final_x_angle <- x_angle
    final_y_angle <- y_angle
  }

  # Color & Geom
  if (is_uniform_color) {
    chosen_color <- sample(color_palette_hex, 1)
    p <- p + geom_bar(stat = "identity", fill = chosen_color,
                      color = bar_stroke_color, linewidth = bar_stroke_size)
    legend_pos <- "none" # Force no legend if uniform
  } else {
    # Varied Color
    schemes <- c("Set2", "Accent", "Dark2", "Paired", "Set1") # Mapping approximate RColorBrewer schemes
    chosen_scheme <- sample(schemes, 1)

    # We must add fill=Category to aes
    if (is_vertical) {
      p <- ggplot(df, aes(x = Category, y = Value, fill = Category))
    } else {
      p <- ggplot(df, aes(y = Category, x = Value, fill = Category))
    }

    p <- p + geom_bar(stat = "identity", color = bar_stroke_color, linewidth = bar_stroke_size) +
      scale_fill_brewer(palette = chosen_scheme)
  }

  # Labels and Titles
  p <- p + labs(title = title_text, subtitle = subtitle_text, x = NULL, y = NULL)

  # Theme Construction
  t <- theme_minimal() +
    theme(
      # Backgrounds
      panel.background = element_rect(fill = bg_color, color = NA),
      plot.background = element_rect(fill = bg_color, color = NA),

      # Outline (View Stroke)
      panel.border = if (has_view_outline) element_rect(color = "black", fill = NA, size = 1) else element_blank(),

      # Grid Lines
      panel.grid.major.x = if (show_grid_x) element_line(color = "lightgrey") else element_blank(),
      panel.grid.minor.x = element_blank(),
      panel.grid.major.y = if (show_grid_y) element_line(color = "lightgrey") else element_blank(),
      panel.grid.minor.y = element_blank(),

      # Axis Labels (Visibility and Color)
      axis.text.x = if (show_x_labels) element_text(angle = final_x_angle, color = label_color, hjust = if(final_x_angle!=0) 1 else 0.5) else element_blank(),
      axis.text.y = if (show_y_labels) element_text(angle = final_y_angle, color = label_color) else element_blank(),

      # Title
      plot.title = plot_title_element,
      plot.subtitle = element_text(hjust = if(runif(1)<0.79) 0.5 else 0),

      # Legend
      legend.position = legend_pos,
      legend.background = legend_box_background,
      legend.title = if (runif(1) >= 0.10) element_blank() else element_text()
    )

  p <- p + t
  return(p)
}

# --- Generate a Chart ---
chart <- generate_random_ggplot()
print(chart)