# Energy Price Forecasting in EMHASS

This document explains how to extend EMHASS's existing machine learning forecaster capabilities to generate energy price forecasts beyond the typical 24-36 hour day-ahead market availability. This enables better 48-hour optimization for battery storage and thermal systems.

## The Challenge

**Day-Ahead Market Limitations:**
- Day-ahead energy prices are typically published 24-36 hours in advance
- For optimal battery scheduling and thermal storage, 48-hour forecasts are preferable
- This creates a gap where the second day of optimization lacks real price data

**Solution:**
Extend EMHASS's MLForecaster to predict energy prices for the missing period, enabling full 48-hour optimization with both historical prices (day 1) and forecasted prices (day 2).

## Architecture Overview

### Current vs Extended System

**Current Price Handling:**
```
Day-ahead prices (24-36h) → EMHASS Optimization → Battery/Thermal Schedule
```

**Extended Price Forecasting:**
```
Historical prices + ML Forecaster → 48h price forecast → Enhanced Optimization
├── Day 1: Real day-ahead prices
└── Day 2: ML forecasted prices
```

## Implementation Approach

### 1. Energy Price Data Collection

First, ensure EMHASS collects comprehensive energy price history:

**Enhanced configuration for price data collection:**
```yaml
retrieve_hass_conf:
  # Standard energy sensors
  var_PV: "sensor.power_photovoltaics"
  var_load: "sensor.power_load_no_var_loads"
  
  # Energy price sensors (multiple sources)
  load_cost: "sensor.nordpool_kwh_price"
  prod_price: "sensor.nordpool_kwh_sell_price"
  gas_cost: "sensor.gas_price_kwh"
  
  # Additional price data for forecasting
  price_forecast_sensors:
    electricity_spot: "sensor.nordpool_kwh_price"
    electricity_day_ahead: "sensor.nordpool_day_ahead"
    gas_daily: "sensor.gas_price_daily"
    grid_tariff: "sensor.grid_tariff_kwh"
    
  # Price forecasting configuration
  price_forecasting:
    enabled: true
    historic_days_to_retrieve: 365  # Full year for seasonal patterns
    forecast_horizon_hours: 48
    price_types: ["electricity", "gas"]
    computational_optimization: true  # Enable efficiency features
```

### 2. ML Forecaster Extension for Energy Prices

**New endpoint: `/action/forecast-price-fit`**

Train price forecasting models using the same MLForecaster framework:

```python
# Runtime parameters for price forecasting
runtimeparams = {
    "historic_days_to_retrieve": 365,  # Full year for seasonal patterns
    "model_type": "electricity_price_forecast",
    "var_model": "sensor.nordpool_kwh_price",
    "sklearn_model": "ElasticNet",  # Good for price data
    "num_lags": 168,  # 1 week of hourly data
    "split_date_delta": "48h",
    "perform_backtest": True,
    
    # Price-specific features
    "add_calendar_features": True,  # Day of week, month, season
    "add_load_features": True,     # Historical load correlation
    "add_renewable_features": True, # Weather/renewable correlation
    "add_weather_features": True,  # Temperature, wind, solar irradiance
}
```

**API Usage:**
```bash
# Fit electricity price forecasting model
curl -i -H "Content-Type:application/json" -X POST -d '{
    "model_type": "electricity_price_forecast",
    "var_model": "sensor.nordpool_kwh_price", 
    "sklearn_model": "ElasticNet",
    "num_lags": 168,
    "historic_days_to_retrieve": 365
}' http://localhost:5000/action/forecast-price-fit

# Fit gas price forecasting model  
curl -i -H "Content-Type:application/json" -X POST -d '{
    "model_type": "gas_price_forecast",
    "var_model": "sensor.gas_price_kwh",
    "sklearn_model": "LinearRegression", 
    "num_lags": 48,
    "historic_days_to_retrieve": 365
}' http://localhost:5000/action/forecast-price-fit
```

### 3. Price Forecasting Prediction

**New endpoint: `/action/forecast-price-predict`**

Generate price forecasts for the optimization horizon:

```bash
# Generate electricity price forecast
curl -i -H "Content-Type:application/json" -X POST -d '{
    "model_type": "electricity_price_forecast",
    "forecast_hours": 48
}' http://localhost:5000/action/forecast-price-predict

# Generate gas price forecast
curl -i -H "Content-Type:application/json" -X POST -d '{
    "model_type": "gas_price_forecast", 
    "forecast_hours": 48
}' http://localhost:5000/action/forecast-price-predict
```

### 4. Enhanced Optimization Integration

**Modified optimization workflow:**

```python
def get_enhanced_price_forecast(self):
    """Get 48-hour price forecast combining real + predicted prices."""
    
    # Get available day-ahead prices (0-36 hours)
    day_ahead_prices = self.get_day_ahead_prices()
    
    # Determine forecast gap
    hours_available = len(day_ahead_prices)
    hours_needed = 48
    forecast_gap = hours_needed - hours_available
    
    if forecast_gap > 0:
        # Use ML forecaster for missing hours
        price_forecast = self.ml_price_forecaster.predict(
            forecast_hours=forecast_gap
        )
        
        # Combine real + forecasted prices
        combined_prices = pd.concat([
            day_ahead_prices,
            price_forecast
        ])
    else:
        combined_prices = day_ahead_prices[:48]
    
    return combined_prices
```

## Configuration Examples

### 1. Simple Electricity Price Forecasting

**Configuration:**
```yaml
optim_conf:
  load_cost_forecast_method: "ml_forecaster"
  
  price_forecasting:
    electricity:
      enabled: true
      model_type: "electricity_price_forecast"
      sklearn_model: "ElasticNet"
      num_lags: 168  # 1 week
      retrain_frequency_days: 7
      
    gas:
      enabled: false  # Use constant gas price
```

**Usage:**
```bash
# Train model (run weekly)
curl -X POST http://localhost:5000/action/forecast-price-fit

# Use in optimization (automatic)
curl -X POST -d '{"load_cost_forecast_method": "ml_forecaster"}' \
  http://localhost:5000/action/perfect-optim
```

### 2. Advanced Multi-Energy Forecasting

**Configuration:**
```yaml
optim_conf:
  price_forecasting:
    electricity:
      enabled: true
      model_type: "electricity_price_forecast"
      sklearn_model: "ElasticNet"
      num_lags: 168
      external_features:
        - "sensor.load_forecast_total"
        - "sensor.wind_power_forecast"
        - "sensor.solar_forecast_total"
        
    gas:
      enabled: true
      model_type: "gas_price_forecast"
      sklearn_model: "LinearRegression"
      num_lags: 48
      seasonal_adjustment: true
      
    dynamic_tariffs:
      enabled: true
      model_type: "grid_tariff_forecast"
      peak_hour_prediction: true
```

## Price Forecasting Features

### 1. Calendar-Based Features

The forecaster automatically adds time-based features that are crucial for energy price forecasting:

**Built-in Features:**
- Hour of day (0-23)
- Day of week (0-6)
- Month of year (1-12)
- Season indicator
- Holiday indicators
- Weekend/weekday flags

### 2. Energy System Features

**Load Correlation Features:**
```python
def add_energy_system_features(self, data):
    """Add energy system features for price forecasting."""
    
    # Historical load patterns
    data['load_ma_24h'] = data['load'].rolling(24).mean()
    data['load_ma_168h'] = data['load'].rolling(168).mean()
    
    # Renewable generation indicators
    data['solar_capacity_factor'] = data['solar_generation'] / solar_capacity
    data['wind_capacity_factor'] = data['wind_generation'] / wind_capacity
    
    # Grid stress indicators  
    data['peak_demand_ratio'] = data['load'] / data['load'].rolling(168).max()
    data['renewable_ratio'] = (data['solar_generation'] + data['wind_generation']) / data['load']
    
    return data
```

### 3. External Data Integration

**Weather-Based Features:**
```yaml
external_features:
  weather:
    temperature: "sensor.outdoor_temperature"
    wind_speed: "sensor.wind_speed" 
    cloud_coverage: "sensor.cloud_coverage"
    
  system_load:
    regional_demand: "sensor.regional_electricity_demand"
    renewable_forecast: "sensor.renewable_generation_forecast"
    
  market_indicators:
    co2_price: "sensor.co2_allowance_price"
    fuel_prices: "sensor.natural_gas_price_daily"
```

## Advanced Implementation

### 1. Ensemble Price Forecasting

Combine multiple models for better accuracy:

```python
class EnsemblePriceForecaster:
    def __init__(self):
        self.models = {
            'elastic_net': ElasticNet(),
            'knn': KNeighborsRegressor(),
            'random_forest': RandomForestRegressor()
        }
        
    def predict(self, data):
        predictions = {}
        for name, model in self.models.items():
            predictions[name] = model.predict(data)
            
        # Weighted ensemble
        ensemble_pred = (
            0.4 * predictions['elastic_net'] +
            0.3 * predictions['knn'] + 
            0.3 * predictions['random_forest']
        )
        return ensemble_pred
```

### 2. Confidence Intervals

Provide uncertainty estimates for risk management:

```python
def predict_with_confidence(self, data, confidence_level=0.95):
    """Generate price forecast with confidence intervals."""
    
    # Base prediction
    base_forecast = self.forecaster.predict(data)
    
    # Bootstrap for confidence intervals
    bootstrap_predictions = []
    for i in range(100):
        bootstrap_sample = self.resample_training_data()
        temp_model = self.train_model(bootstrap_sample)
        bootstrap_predictions.append(temp_model.predict(data))
        
    # Calculate confidence intervals
    lower_bound = np.percentile(bootstrap_predictions, 
                               (1-confidence_level)/2 * 100, axis=0)
    upper_bound = np.percentile(bootstrap_predictions, 
                               (1+confidence_level)/2 * 100, axis=0)
    
    return {
        'forecast': base_forecast,
        'confidence_lower': lower_bound,
        'confidence_upper': upper_bound
    }
```

## Integration with Optimization

### 1. Risk-Aware Optimization

Use price uncertainty in optimization decisions:

```python
def optimize_with_price_uncertainty(self):
    """Optimize considering price forecast uncertainty."""
    
    # Get price forecast with confidence intervals
    price_forecast = self.get_price_forecast_with_confidence()
    
    # Conservative strategy: use upper confidence bound for costs
    conservative_prices = price_forecast['confidence_upper']
    
    # Optimistic strategy: use lower confidence bound for revenues  
    optimistic_sell_prices = price_forecast['confidence_lower']
    
    # Run optimization with adjusted prices
    return self.optimize(
        load_cost=conservative_prices,
        prod_price=optimistic_sell_prices
    )
```

### 2. Adaptive Model Updates

Automatically retrain models based on forecast accuracy:

```python
def adaptive_model_management(self):
    """Manage model retraining based on performance."""
    
    # Check recent forecast accuracy
    recent_accuracy = self.evaluate_recent_forecasts()
    
    if recent_accuracy < self.accuracy_threshold:
        self.logger.info("Price forecast accuracy below threshold, retraining...")
        
        # Retrain with more recent data
        self.retrain_model(
            historic_days=self.adaptive_training_days,
            include_recent_patterns=True
        )
        
    # Update training schedule based on volatility
    price_volatility = self.calculate_price_volatility()
    if price_volatility > self.volatility_threshold:
        self.training_frequency = "daily"
    else:
        self.training_frequency = "weekly"
```

## Home Assistant Integration

### 1. Price Forecast Sensors

Publish forecasted prices to Home Assistant:

```yaml
# Automated price forecast publishing
price_forecast_publishing:
  enabled: true
  sensors:
    - entity_id: "sensor.electricity_price_forecast_24h"
      friendly_name: "Electricity Price Forecast 24h"
      unit_of_measurement: "€/kWh"
      forecast_hours: 24
      
    - entity_id: "sensor.electricity_price_forecast_48h" 
      friendly_name: "Electricity Price Forecast 48h"
      unit_of_measurement: "€/kWh"
      forecast_hours: 48
      
    - entity_id: "sensor.gas_price_forecast_48h"
      friendly_name: "Gas Price Forecast 48h"
      unit_of_measurement: "€/kWh"
      forecast_hours: 48
```

### 2. Automation Integration

Use price forecasts in Home Assistant automations:

```yaml
automation:
  - alias: "Retrain Price Models Weekly"
    trigger:
      - platform: time
        at: "02:00:00"
      - platform: time
        at: "02:00:00"
        weekday: "sun"
    action:
      - service: rest_command.emhass_price_forecast_fit
        data:
          model_type: "electricity_price_forecast"
          
  - alias: "High Price Period Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.electricity_price_forecast_24h
        above: 0.25  # €/kWh
    action:
      - service: notify.home_assistant
        data:
          message: "High electricity prices forecasted - consider pre-charging battery"
```

## Benefits and Use Cases

### 1. Enhanced Battery Optimization

**48-Hour Battery Strategy:**
- Day 1 (real prices): Detailed arbitrage opportunities
- Day 2 (forecasted prices): Strategic positioning based on expected prices
- Better handling of multi-day price patterns

### 2. Thermal Storage Optimization

**Thermal Buffer Management:**
- Predict price trends for thermal storage charging
- Optimize heat pump vs gas boiler decisions across 48 hours
- Account for both energy prices and weather forecasts

### 3. EV Charging Optimization

**Smart EV Charging:**
- Plan charging sessions based on 48-hour price outlook
- Coordinate with PV production and battery storage
- Optimize for both cost and grid impact

## Why Full Year of Data is Essential

### Seasonal Energy Price Patterns

Energy prices exhibit strong seasonal patterns that require full annual data to capture:

**Summer Patterns:**
- High cooling demand drives peak electricity prices
- High solar generation can suppress midday prices
- Heat waves cause extreme price spikes

**Winter Patterns:**
- High heating demand increases overall prices
- Low renewable generation increases fossil fuel dependency
- Cold snaps drive natural gas and electricity price spikes

**Shoulder Seasons (Spring/Fall):**
- Mild weather creates different demand patterns
- Maintenance seasons affect generation capacity
- Transition periods between heating/cooling seasons

**Weather Impact Examples:**
```python
# Temperature-driven price relationships
seasonal_features = {
    'summer_cooling_degree_days': 'High temps → AC demand → price spikes',
    'winter_heating_degree_days': 'Low temps → heating demand → price increases', 
    'shoulder_season_mild_weather': 'Mild temps → lower demand → lower prices',
    'extreme_weather_events': 'Heat waves/cold snaps → extreme price volatility'
}
```

### Holiday and Calendar Effects

Full year data captures important calendar-driven price patterns:
- **Holiday weeks**: Reduced industrial demand
- **Summer vacation periods**: Different residential patterns  
- **School calendar**: Affects commercial building demand
- **Daylight saving time**: Changes daily demand profiles

## Performance Considerations

### 1. Managing Computational Load

**Data Volume:**
- 365 days × 24 hours = 8,760 hourly data points
- With 168 lags (1 week) = ~9,000 features per prediction
- Modern systems can handle this efficiently

**Optimization Strategies:**

#### A. Efficient Model Selection
```python
# Recommended models for large datasets
efficient_models = {
    'ElasticNet': 'Fast, handles multicollinearity, built-in regularization',
    'LinearRegression': 'Fastest for simpler patterns',
    'SGDRegressor': 'Good for very large datasets with online learning'
}

# Avoid for large datasets
avoid_models = {
    'KNeighborsRegressor': 'Memory intensive, slow predictions',
    'RandomForest': 'Can be slow with many features'
}
```

#### B. Feature Engineering Optimization
```python
def optimize_features_for_yearly_data(self):
    """Optimize feature set for computational efficiency."""
    
    # Use feature selection to reduce dimensionality
    from sklearn.feature_selection import SelectKBest, f_regression
    
    # Select top 50 most important features
    selector = SelectKBest(score_func=f_regression, k=50)
    
    # Prioritize features by importance
    priority_features = [
        'hour_of_day', 'day_of_week', 'month',  # Calendar
        'temperature', 'heating_degree_days',    # Weather
        'load_24h_ma', 'renewable_ratio',        # Energy system
        'price_lag_24', 'price_lag_168'          # Price history
    ]
    
    return selector, priority_features
```

#### C. Incremental Learning Approach
```python
def incremental_training_strategy(self):
    """Strategy for managing yearly data training."""
    
    # Initial training with full year
    initial_training = {
        'data_period': '365 days',
        'frequency': 'monthly',  # Full retrain monthly
        'trigger': 'scheduled'
    }
    
    # Incremental updates with recent data
    incremental_updates = {
        'data_period': '30 days',
        'frequency': 'weekly',   # Update with recent patterns
        'trigger': 'performance_threshold'
    }
    
    return initial_training, incremental_updates
```

### 2. Memory Management

**Chunked Processing:**
```python
def chunked_data_processing(self, chunk_size_days=30):
    """Process yearly data in chunks to manage memory."""
    
    total_days = 365
    chunks = []
    
    for start_day in range(0, total_days, chunk_size_days):
        end_day = min(start_day + chunk_size_days, total_days)
        
        # Process chunk
        chunk_data = self.load_data_chunk(start_day, end_day)
        processed_chunk = self.preprocess_chunk(chunk_data)
        chunks.append(processed_chunk)
        
    # Combine chunks efficiently
    return self.combine_chunks(chunks)
```

### 3. Model Training Frequency

**Recommended Schedule with Yearly Data:**
- **Full retrain**: Monthly (using all 365 days)
- **Incremental update**: Weekly (using last 30 days to adjust recent patterns)
- **Emergency retrain**: When MAPE > 15% for 3 consecutive days

**Training Strategy:**
```yaml
training_schedule:
  full_retrain:
    frequency: "monthly"
    data_period: "365 days"
    trigger: "scheduled"
    
  incremental_update:
    frequency: "weekly" 
    data_period: "30 days"
    trigger: "performance_degradation"
    
  emergency_retrain:
    frequency: "as_needed"
    data_period: "90 days"  # Recent focus
    trigger: "accuracy_threshold"
```

### 4. Computational Benchmarks

**Expected Performance (typical home server):**

| Operation | Data Size | Time | Memory |
|-----------|-----------|------|---------|
| Data Loading | 365 days hourly | 2-5 seconds | 50-100 MB |
| Feature Engineering | 8,760 points | 10-30 seconds | 200-500 MB |
| Model Training (ElasticNet) | Full dataset | 30-120 seconds | 300-800 MB |
| Prediction (48h) | Loaded model | <1 second | 10-50 MB |

**Hardware Recommendations:**
- **Minimum**: 4GB RAM, dual-core CPU
- **Recommended**: 8GB RAM, quad-core CPU  
- **Optimal**: 16GB RAM, 6+ core CPU

### 5. Storage Optimization

**Efficient Data Storage:**
```python
# Compressed storage for historical data
storage_optimization = {
    'format': 'parquet',  # ~50% smaller than CSV
    'compression': 'snappy',  # Fast compression/decompression
    'partitioning': 'by_month',  # Enable partial loading
    'schema_optimization': 'float32',  # vs float64 for space savings
}

# Example: 365 days of hourly data
# CSV: ~2-5 MB
# Parquet (compressed): ~800KB - 1.5MB
```

## Conclusion

Energy price forecasting extends EMHASS's capabilities from reactive (using only available prices) to predictive (generating needed price forecasts). This enables:

- **True 48-hour optimization** instead of 24-36 hour optimization
- **Better battery arbitrage** with longer planning horizon
- **Improved thermal storage management** with price trend awareness
- **Risk management** through forecast uncertainty quantification

The implementation leverages EMHASS's existing MLForecaster framework, making it a natural extension that integrates seamlessly with current optimization workflows while providing significant value for energy management applications. 