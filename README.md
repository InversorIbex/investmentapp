# Inversor Íbex

Terminal local para el inversor particular. Screener de Estados Unidos, Canadá y Europa, gangas, calidad, reyes y aristócratas del dividendo, termómetro, noticias, calendario de resultados, sentimiento y una cartera de papel de 10 nombres.

No es asesoramiento ni una recomendación de compra o venta. Las cotizaciones son diferidas.

## Arranque

En esta carpeta:

```bat
iniciar.bat
```

O, si Python ya tiene las zonas horarias:

```bat
python server.py
```

Se abre en [http://127.0.0.1:8787/](http://127.0.0.1:8787/). Solo escucha en el propio ordenador. Para arrancar sin abrir el navegador: `set IBEX_OPEN=0` y luego `python server.py`.

Hace falta Python 3.12 o superior. `tzdata` se instala sola si Windows no trae la zona `Europe/Madrid`. Flask solo hace falta para el despliegue.

## Vercel

El repositorio ya trae `app.py`, `requirements.txt` y `.python-version`. La web estática está en `public/` y la sirve la CDN. La API es Flask: Vercel carga `app.py` sin archivo de configuración. No hace falta `vercel.json`. Un bloque `functions` sobre `app.py` en la raíz falla el build, porque ese patrón solo vale para archivos dentro de `api/`.

1. En Vercel, importa `InversorIbex/investmentapp`.
2. El marco es Flask. No hace falta comando de build ni variables de entorno.
3. Despliega.

La primera visita a Gangas o a Hoy puede tardar, porque baja datos de Yahoo y de la SEC. El tope por defecto de la función es 300 segundos. La caché y la cartera de papel en Vercel viven en el disco temporal de la función: se vacían cuando Vercel recicla la instancia. En este ordenador la cartera sigue en `data/portfolio.json`.

## Qué hay en cada apartado

- **Hoy.** Temperatura, sesiones, seis índices, titulares y la cartera de papel.
- **Índices.** Plazas grandes de América, Europa y Asia, más VIX, bonos, dólar, oro y petróleo.
- **Screener.** Filtros de Yahoo sobre capitalización, PER, dividendo, ROE, crecimiento y el recorrido de doce meses. La nota de calidad se calcula aquí.
- **Gangas.** En Estados Unidos, ingresos al alza en cada uno de los últimos cinco ejercicios (10-K de la SEC), beneficio neto positivo y la acción pierde más de un 8% a doce meses. En Canadá y Europa Yahoo solo publica cuatro ejercicios: se piden tres subidas seguidas y la misma caída. La primera visita tarda, porque descarga los hechos de la SEC.
- **Calidad.** Bolsa de origen, ROE por encima del 8% y margen neto por encima del 4%. Se quitan CDRs, preferentes y la misma acción repetida en Fráncfort, Zúrich o Viena.
- **Dividendos.** Reyes: censo público de 60 empresas a 1 de noviembre de 2026. Aristócratas del S&P 500: 68 nombres a 2 de noviembre de 2026, sin Kenvue. La columna de años es la de Yahoo y a menudo se queda corta. Esta web no recalcula la racha.
- **Termómetro y sentimiento.** CNN Fear & Greed, amplitud de Nueva York, VIX y el día de los índices.
- **Noticias.** Titulares en español de Google News.
- **Resultados.** Calendario de unas tres semanas. El beneficio estimado es el consenso de Yahoo, no un análisis de esta web.
- **Cartera modelo.** Papel de 100.000 euros en diez nombres. Cada día laborable, hora de Madrid, como mucho un cambio: se vende la peor solo si una de fuera la gana por 8 puntos o más. Con el miedo de CNN por debajo de 25 no se vende una posición que siga en 45. La referencia es 50% S&P 500, 30% Euro Stoxx 50 y 20% TSX, en euros.

## Datos

Yahoo Finance para cotizaciones, screener y calendario. SEC EDGAR para la racha de ingresos de Estados Unidos. CNN para el índice de miedo y codicia. Las listas de reyes y aristócratas salen del censo público de Sure Dividend de noviembre de 2026: marcan la pertenencia, no inventan años.

La caché vive en `data/cache/`. La cartera de papel, en `data/portfolio.json`. Ninguna de las dos se sube a git.
