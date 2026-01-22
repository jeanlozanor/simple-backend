# Simple API - Nuevas Features

## 🎯 Endpoints Implementados

### 1. **Búsqueda en Todas las Tiendas**
```
POST /search/all-stores
```
**Busca en:** Hiraoka, Falabella, Alkosto, Promart, Oechsle, PlazaVea

**Features:**
- Corrección automática de ortografía
- Filtrado inteligente por intención de búsqueda
- Eliminación de duplicados
- Ordenamiento por precio

**Ejemplo:**
```json
{
  "query": "pura"
}
```

---

### 2. **Recomendaciones Inteligentes**
```
POST /search/recommendations
```

**Features:**
- Análisis de precios (productos baratos reciben más puntos)
- Puntos por tienda confiable (Hiraoka, Falabella)
- Ranking automático por relevancia
- Score de 0-100 para cada producto

**Response:**
```json
{
  "recommendations": [
    {
      "product": { ... },
      "reason": "Muy buen precio; Vendido por Hiraoka Online",
      "score": 98.5
    }
  ],
  "total": 10,
  "message": "Se generaron 10 recomendaciones..."
}
```

---

### 3. **Comparativa de Precios**
```
POST /search/compare-prices
```

**Features:**
- Encuentra el mismo producto en múltiples tiendas
- Calcula ahorros potenciales en porcentaje
- Muestra precio mínimo y máximo
- Ordena por ahorro potencial

**Response:**
```json
{
  "comparisons": [
    {
      "product_name": "Smartphone Pura 80",
      "cheapest": { "store_name": "Hiraoka Online", "price": 2499 },
      "most_expensive": { "store_name": "Falabella Online", "price": 2599 },
      "price_difference": 100,
      "average_price": 2549,
      "savings_percentage": 3.85
    }
  ],
  "total": 5
}
```

---

### 4. **Estadísticas de Precios**
```
POST /search/statistics
```

**Features:**
- Precio mínimo, máximo, promedio y mediana
- Muestra en cuántas tiendas está disponible
- Desglose de precios por tienda

**Response:**
```json
{
  "statistics": [
    {
      "product_name": "Smartphone Pura 80",
      "count": 2,
      "min_price": 2499,
      "max_price": 2599,
      "average_price": 2549.0,
      "median_price": 2549.0,
      "stores": {
        "Hiraoka Online": 2499,
        "Falabella Online": 2599
      }
    }
  ],
  "total": 1
}
```

---

## 🤖 Funciones de IA Integradas

### **Corrección Automática de Búsqueda**
- Detecta errores ortográficos
- Sugiere palabras correctas automáticamente
- Mantiene la intención original de búsqueda

### **Filtrado Inteligente**
Entiende intenciones de búsqueda:
- **"barato", "económico", "oferta"** → ordena por precio ascendente
- **"premium", "caro", "lujo"** → filtra productos premium
- **"apple", "samsung", "huawei"** → filtra por marca

### **Scoring Inteligente**
Para recomendaciones:
- +20 puntos si el precio es 20% más bajo que el promedio
- +15 puntos si es vendido por tienda confiable
- +10 puntos por posición en ranking

---

## 📊 Tiendas Soportadas

1. **Hiraoka Online** - https://hiraoka.com.pe
2. **Falabella Online** - https://falabella.com.pe
3. **Alkosto Online** - https://alkosto.com
4. **Promart** - https://www.promart.pe
5. **Oechsle** - https://www.oechsle.pe
6. **PlazaVea** - https://www.plazavea.com.pe

---

## 🔍 Ejemplos de Uso

### Buscar "pura" en todas las tiendas:
```bash
curl -X POST "http://localhost:8000/search/all-stores" \
  -H "Content-Type: application/json" \
  -d '{"query": "pura"}'
```

### Obtener recomendaciones:
```bash
curl -X POST "http://localhost:8000/search/recommendations" \
  -H "Content-Type: application/json" \
  -d '{"query": "celular barato"}'
```

### Comparar precios:
```bash
curl -X POST "http://localhost:8000/search/compare-prices" \
  -H "Content-Type: application/json" \
  -d '{"query": "huawei pura 80"}'
```

### Ver estadísticas:
```bash
curl -X POST "http://localhost:8000/search/statistics" \
  -H "Content-Type: application/json" \
  -d '{"query": "pura"}'
```

---

## ⚡ Mejoras Futuras

- [ ] Historial de búsquedas del usuario
- [ ] Alertas de precio configurables
- [ ] Machine Learning para mejores recomendaciones
- [ ] Integración con más tiendas
- [ ] API de notificaciones por email/SMS
- [ ] Análisis de tendencias de precio
- [ ] Wishlist de usuario
