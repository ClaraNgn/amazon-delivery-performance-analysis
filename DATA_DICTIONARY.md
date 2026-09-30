# Analytical Data Dictionary

The Tableau-ready file is `tableau/amazon_delivery_dashboard_data.csv`.

| Field | Meaning |
|---|---|
| `ID` | Unique delivery identifier |
| `Delivery_person_ID` | Courier identifier from the source |
| `City_Name` | City inferred from the courier ID prefix |
| `Delivery_person_Age` | Courier age after validation and median imputation |
| `Age_Group` | Portfolio-friendly courier age band |
| `Delivery_person_Ratings` | Courier rating after validation and median imputation |
| `Rating_Band` | Rating segment |
| `Weather` | Decoded weather condition |
| `Traffic` | Decoded road-traffic category |
| `Vehicle_condition` | Source vehicle-condition code |
| `Order_Type` | Decoded order category |
| `Vehicle_Type` | Decoded delivery vehicle |
| `multiple_deliveries` | Number of simultaneous deliveries after mode imputation |
| `Festival_Flag` | Whether the delivery occurred during a festival |
| `Time_Orderd` | Source order time |
| `Time_Order_picked` | Source pickup time |
| `Order_Hour` | Normalized hour of order |
| `Order_Period` | Morning, afternoon, evening, late night, or unknown |
| `Pickup_Delay_Min` | Minutes between order and pickup; values over 120 removed |
| `Restaurant_latitude`, `Restaurant_longitude` | Validated restaurant coordinates |
| `Delivery_location_latitude`, `Delivery_location_longitude` | Validated destination coordinates |
| `Distance_KM` | Straight-line Haversine distance for plausible coordinates |
| `Time_taken(min)` | Delivery time in minutes; analysis target |
| `Delivery_Count` | Constant 1 for Tableau row-count KPIs |
| `On_Time_Flag` | 1 when delivery time is 30 minutes or less, otherwise 0 |
| `Delivery_Speed_Band` | Fast (≤20m), standard (21–30m), or slow (>30m) |
| `On_Time_30m` | Text label for the project’s 30-minute benchmark |

