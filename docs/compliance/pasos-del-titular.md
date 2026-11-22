# Pasos manuales del titular

Esta guía junta todo lo que **solo David puede hacer**: lo que pide su cuenta, sus claves, su
dinero o a personas reales. Los agentes avanzaron todo lo demás. Al terminar cada paso, basta con
escribir **«listo, paso N»** en el chat de Claude: el agente comprueba y continúa.

!!! danger "Reglas para todos los pasos"
    - **Nunca pegues una clave, un secreto, un código 2FA ni una contraseña en el chat**, en
      Jira o en GitHub. Las claves van solo en el archivo `.env`, o se escriben cuando el script
      las pide (no se ven ni se guardan).
    - Ninguna clave de Binance lleva **permiso de retiro**. Nunca.
    - Las capturas que compartas no deben mostrar nombre, documento, UID, saldo ni claves.

## Resumen y orden recomendado

| Paso | Qué | Tiempo | Desbloquea |
|---|---|---|---|
| [1](#paso-1-comisiones-reales-de-binance-pq-17) | Comisiones reales de Binance, sin operar | 15 min | 5 evaluaciones retenidas (PQ-68, PQ-66, PQ-69, PQ-114, PQ-94), lo que depende de ellas (PQ-82, PQ-101) y el holdout del carry |
| [2](#paso-2-claves-de-binance-demo-pq-51-pq-52-pq-95) | Claves de Binance Demo | 10 min | PQ-51, PQ-52 y PQ-95 (ejecución en Demo) |
| [3](#paso-3-clave-de-anthropic-para-pregunta-pq-90) | Clave de Anthropic para `/pregunta` | 10 min | El asistente del bot de Telegram (PQ-90) |
| [4](#paso-4-prueba-de-usabilidad-con-3-personas-pq-76) | Prueba de usabilidad con 3 personas | 1 h y media | PQ-76 (cap. 7.2 del informe) |
| [5](#paso-5-claves-de-bybit-testnet-pq-100) | Claves de Bybit testnet | 10 min | PQ-100 (segundo exchange en paper) |
| [6](#paso-6-hacer-publica-la-imagen-del-dashboard-pq-81) | Hacer pública la imagen del dashboard en GHCR | 2 min | El despliegue en la VM sin credenciales (PQ-57) |
| [7](#paso-7-mantener-la-laptop-encendida) | Mantener la laptop encendida | 5 min | Que el paper trading siga 24/7 mientras no hay VM |
| [8](#paso-8-opcional-revisar-los-pre-registros) | Opcional: revisar los pre-registros | 20 min | Nada; da tranquilidad antes de las ejecuciones que cuentan en N |

Sin el paso 1 no se puede correr ninguna evaluación de investigación: cada una cuenta en N y no
tiene vuelta atrás.

## Paso 1. Comisiones reales de Binance (PQ-17)

**Objetivo:** saber, sin hacer ninguna operación, cuatro cosas:

- el nivel VIP de la cuenta y si está verificada (KYC);
- si están habilitados los futuros USDⓈ-M y el margin;
- las comisiones maker y taker reales de spot y de futuros USDⓈ-M;
- si el descuento por pagar con BNB está activo.

Hay dos caminos. El **A** da los números exactos de tu cuenta; el **B** solo usa la web. Si
puedes, haz el A; si algo falla, el B.

### Camino A (recomendado): script con una clave de solo lectura

El script `scripts/comisiones_binance.py`:

- solo hace consultas `GET`: no opera, no mueve fondos y no guarda la clave;
- empieza por comprobar los permisos de la propia clave y **se niega a seguir** si tiene algo
  más que lectura.

**1. Crear la clave de solo lectura** (en la cuenta real de Binance, desde el navegador):

1. Entra en <https://www.binance.com> e inicia sesión.
2. Abre la **gestión de API**, de una de estas dos formas:
   - icono de perfil (arriba a la derecha) → **Cuenta** → **Gestión de API**;
   - directamente <https://www.binance.com/es/my/settings/api-management>.
3. Pulsa **Crear API** → elige **Generada por el sistema** → nombre: `pq-solo-lectura`.
4. Confirma con tu 2FA (correo, SMS o app de autenticación). El código no se lo pases a nadie.
5. Binance muestra la **API Key** y la **Secret Key**. La Secret Key **solo se ve esta vez**:
   déjala en esa pestaña abierta hasta terminar el paso 3.
6. Pulsa **Editar restricciones** en la clave nueva y deja **solo** «Habilitar lectura» (*Enable
   Reading*). Todo lo demás debe quedar **desmarcado**:
   - trading de spot y margin;
   - futuros;
   - retiros;
   - transferencia universal y transferencias internas;
   - opciones.

   En «Restricción de acceso por IP» puedes dejar «Sin restricción»: una clave de solo lectura
   lo permite, y la vas a borrar en 10 minutos. Guarda los cambios.

**2. Ejecutar el script** (en la terminal de Ubuntu/WSL):

```bash
cd ~/code/prometheus-platform && git pull
uv run python scripts/comisiones_binance.py
```

Te pedirá `API Key:` y luego `Secret Key:`. Pega cada una con clic derecho (o `Ctrl+Shift+V`) y
pulsa Enter. **No se ve nada mientras pegas**: es normal, así no queda en pantalla.

**3. Qué esperar:**

- **Si todo va bien,** imprime una tabla así (los números serán los de tu cuenta):

  ```text
  | Comprobación | Resultado | Fecha |
  |---|---|---|
  | Nivel VIP | VIP 0 | 2026-11-22 |
  | Margin habilitado | sí | 2026-11-22 |
  | Futuros USDⓈ-M habilitados | sí | 2026-11-22 |
  | Comisión spot BTCUSDT maker / taker | 0,100 % / 0,100 % (sin descuento BNB activo) | 2026-11-22 |
  | Comisión USDⓈ-M BTCUSDT maker / taker | 0,020 % / 0,050 % | 2026-11-22 |
  ```

  **Cópiala y pégala en el chat.** No contiene claves ni datos personales.
- **Si dice «ALTO: la clave tiene permisos además de lectura»,** no consultó nada. Vuelve al
  punto 1.6, desmarca lo que nombra y repite.
- **Si la fila de USDⓈ-M dice «no legible con clave de solo lectura»,** Binance exige el permiso de
  futuros incluso para leer. **No lo actives.** Mira esa fila en la web (camino B, punto 3).
- **Si dice «Futuros USDⓈ-M habilitados: no»,** también es un dato válido: pégalo igual. El
  agente abre el ticket para replantear la Estrategia 1 con otro exchange (lo pide PQ-17).

**4. Borrar la clave:** vuelve a **Gestión de API** → **Eliminar** en `pq-solo-lectura`. Ya no
hace falta.

### Camino B: solo con la web

1. **KYC y nivel VIP:**
   - Entra en icono de perfil → **Panel** (*Dashboard*). Arriba, junto a tu usuario, aparecen
     el nivel («Usuario normal» o «Regular» es VIP 0) y una marca de **Verificado**.
   - El detalle del KYC está en **Cuenta** → **Verificación de identidad**.
2. **Comisiones de spot:** abre <https://www.binance.com/es/fee/trading> con la sesión iniciada.
   - La tabla marca tu nivel. Anota el maker y el taker de esa fila, la columna **sin** BNB.
   - En **Panel**, busca el interruptor «Usar BNB para pagar comisiones» (*BNB deduction*).
     Anota si está **activado** o **desactivado**.
3. **Comisiones de futuros USDⓈ-M:** abre <https://www.binance.com/es/fee/futureFee> con la
   sesión iniciada, pestaña **USDⓈ-M**, y anota el maker y el taker de tu nivel.
   - Si la página no muestra cifras, entra en la pantalla de trading de futuros:
     <https://www.binance.com/es/futures/BTCUSDT>.
   - Al pie del formulario de órdenes hay un enlace **«Nivel de comisión»** (*Fee level*) con
     tus tasas. **No pulses Comprar ni Vender.**
4. **¿Futuros habilitados?** En esa misma pantalla de futuros pueden pasar tres cosas:
   - **Ves el gráfico y el formulario de órdenes:** están habilitados.
   - **Ves «Abrir ahora»** (*Open Now*) con un cuestionario: están **disponibles pero sin
     abrir**. Puedes completar el cuestionario. Abrir la cuenta de futuros no deposita dinero ni
     opera; anota «disponible, cuestionario completado el <fecha>».
   - **Ves «no disponible en tu país o región»:** anota exactamente ese texto.
5. **¿Margin habilitado?** Menú **Trade** → **Margin**: mismas tres posibilidades que en
   futuros.

**Qué mandar por el chat** (copia y completa):

```text
Paso 1 (camino B), fecha: AAAA-MM-DD
KYC: verificado / no verificado (nivel: ...)
Nivel VIP: ...
Spot maker / taker: ... % / ... %
Descuento BNB: activado / desactivado
USDⓈ-M maker / taker: ... % / ... %
Futuros USDⓈ-M: habilitados / disponibles tras cuestionario / no disponibles
Margin: habilitado / disponible tras cuestionario / no disponible
```

### Qué hace el agente con eso

1. Completa la sección 3 de [binance.md](binance.md) con la fecha y cierra PQ-17.
2. **Si las comisiones son iguales o menores que las del modelo** (spot 0,100 %, USDⓈ-M
   0,020 % / 0,050 %), ejecuta **una vez** cada evaluación retenida y documenta los resultados:
   - PQ-68 (tendencia);
   - PQ-66 (H1 y H2 tras KE-014 y KE-016);
   - PQ-69 (H3);
   - PQ-114 (momentum transversal);
   - PQ-94.
3. **Si son más altas,** primero enmienda los pre-registros con fecha, y después ejecuta.
4. **El holdout del carry no se abre sin ti:** se abre una sola vez y con el titular presente.

## Paso 2. Claves de Binance Demo (PQ-51, PQ-52, PQ-95)

Binance Demo (*Demo Trading*) es un entorno con dinero ficticio. Sus claves **no sirven** en la
cuenta real.

1. Entra en <https://demo.binance.com> con tu cuenta de Binance de siempre. Si pregunta, acepta
   activar el modo demo.
2. Icono de perfil → **Gestión de API** → **Crear API** → **Generada por el sistema** → nombre
   `pq-demo`.
3. Permisos: **lectura**, **trading de spot** y **futuros**. **Nunca retiros.**
4. Copia la API Key y la Secret Key. Pégalas en el `.env` de la plataforma, desde la terminal:

   ```bash
   nano ~/code/prometheus-platform/.env
   ```

   Busca estas tres líneas (si no están, agrégalas al final) y deja solo tus valores después del
   `=`, sin espacios ni comillas:

   ```text
   PQ_BINANCE_API_KEY=pega-aqui-la-api-key
   PQ_BINANCE_API_SECRET=pega-aqui-la-secret-key
   PQ_BINANCE_TESTNET=true
   ```

   Guarda con `Ctrl+O`, Enter, y sal con `Ctrl+X`.
5. Comprueba que quedaron, **sin mostrarlas**:

   ```bash
   grep -cE '^PQ_BINANCE_API_(KEY|SECRET)=.+' ~/code/prometheus-platform/.env   # debe decir 2
   ```

6. Escribe «listo, paso 2» en el chat. El agente las copia a su worktree sin leerlas en voz alta.
   `PQ_BINANCE_TESTNET=true` hace que la configuración rechace cualquier intento de usarlas
   fuera de Demo (PQ-15).

## Paso 3. Clave de Anthropic para `/pregunta` (PQ-90)

El bot de Telegram ya tiene el comando `/pregunta`. Responde preguntas en lenguaje natural sobre
el paper trading con herramientas de solo lectura, y tiene un tope de gasto diario. Solo le falta
la clave.

1. Entra en <https://console.anthropic.com> con la cuenta que quieras pagar.
2. **Billing:** agrega crédito. Con el tope de 1 USD/día, 5 USD duran semanas. Puedes poner
   también un límite mensual del *workspace* en **Settings** → **Limits**.
3. **Settings** → **API Keys** → **Create Key** → nombre `pq-bot` → copia la clave (empieza por
   `sk-ant-`; solo se muestra una vez).
4. Agrégala a **los dos** `.env`: el de la plataforma y el del runtime que ejecuta el bot.

   ```bash
   nano ~/code/prometheus-platform/.env
   nano ~/code/pq-runtime/.env
   ```

   En cada uno:

   ```text
   PQ_ANTHROPIC_API_KEY=pega-aqui-la-clave
   PQ_ASSISTANT_DAILY_LIMIT_USD=1
   ```

5. Escribe «listo, paso 3». El agente arranca `pq paper bot` en el runtime (hoy no está
   corriendo) y prueba `/pregunta ¿cómo va el paper?` desde el grupo de alertas.

## Paso 4. Prueba de usabilidad con 3 personas (PQ-76)

El protocolo completo está en
[prueba-de-usabilidad.md](../academico/prueba-de-usabilidad.md). Las tareas están fijadas antes de
las sesiones, así que no se pueden cambiar después. En resumen:

1. Busca a **3 personas no técnicas**: familia, amigos o compañeros de otra carrera. No pueden
   ser del equipo.
2. Para cada una (unos 20 a 25 minutos):
   - Abre el dashboard en <http://localhost:8501>. Está corriendo en la laptop.
   - Lee el guion del moderador tal como está escrito.
   - Pídele que piense en voz alta.
   - **No la ayudes**, aunque se trabe.
3. Anota, por tarea:
   - si la completó;
   - cuánto tardó;
   - dónde dudó o se equivocó;
   - la puntuación SUS del final.
4. Pasa las notas al chat (sin nombres; «Persona 1, 2, 3»). El agente llena la tabla de resultados
   y propone las mejoras.

## Paso 5. Claves de Bybit testnet (PQ-100)

1. Entra en <https://testnet.bybit.com> y **regístrate aparte**: la testnet es una cuenta distinta
   de la de Bybit real.
2. Pide fondos de prueba: menú de activos → **Request test coins** (o «Solicitar monedas de
   prueba»).
3. Icono de perfil → **API** → **Create New Key** → **System-generated API Keys**:
   - uso: *API Transaction*; nombre: `pq-testnet`;
   - permisos: **Read-Write**, marcando solo **Contracts → Orders y Positions** y **Spot →
     Trade**;
   - **nada de Wallet, retiros ni transferencias**;
   - IP: sin restricción, porque es testnet.
4. Agrégalas al `.env` de la plataforma (`nano ~/code/prometheus-platform/.env`):

   ```text
   PQ_BYBIT_API_KEY=pega-aqui-la-api-key
   PQ_BYBIT_API_SECRET=pega-aqui-el-secret
   PQ_BYBIT_TESTNET=true
   ```

   Son los nombres que usará el adaptador de PQ-100.
5. Escribe «listo, paso 5».

## Paso 6. Hacer pública la imagen del dashboard (PQ-81)

Desde el 22-nov, la CI publica la imagen firmada del dashboard en GitHub Container Registry
(GHCR). GHCR la crea privada. La imagen no contiene secretos, solo el código, que ya es público.

1. Abre <https://github.com/orgs/PrometheusQuant/packages> → `pq-dashboard` → **Package
   settings**.
2. Al final, en **Danger Zone** → **Change visibility** → **Public** → escribe el nombre para
   confirmar.

Es opcional hasta que exista la VM (PQ-57). La alternativa es darle a la VM un token de solo
lectura; ver [cadena de suministro](../runbooks/cadena-de-suministro.md).

## Paso 7. Mantener la laptop encendida

Mientras no haya VM en Oracle, el paper trading corre en la laptop:

- el runner;
- el vigilante;
- el dashboard en el puerto 8501.

Si Windows suspende la laptop, se detiene todo. El vigilante avisa por Telegram y el runner se
reconcilia solo al volver.

1. **Windows → Configuración → Sistema → Energía y batería → Pantalla, suspensión e hibernación:**
   «Cuando esté enchufado, suspender el dispositivo después de» → **Nunca**. La pantalla sí puede
   apagarse.
2. **Panel de control → Opciones de energía → Elegir el comportamiento al cerrar la tapa:**
   «Enchufado» → **No hacer nada**.
3. **Windows Update → Opciones avanzadas → Horas activas:** pon el rango en que usas la laptop,
   para que no reinicie de día. Si reinicia, al volver dile al agente «reinició la laptop» y él
   levanta todo de nuevo.
4. Déjala enchufada.

Para comprobar que todo sigue vivo, en la terminal:

```bash
cat ~/code/prometheus-platform/data/paper/heartbeat.json; echo; date -u
```

Interpreta la salida así:

- `"at"` es el último latido del runner, en hora UTC. Debe estar a menos de 10 minutos de la
  hora que imprime `date -u`.
- `"ok": true` significa que el último ciclo terminó bien.

El dashboard sigue en <http://localhost:8501>. El runtime lee y escribe en
`~/code/prometheus-platform/data/` (no en `~/code/pq-runtime/data/`, que es una copia vieja).

## Paso 8. Opcional: revisar los pre-registros

Antes de que el agente ejecute las evaluaciones del paso 1, puedes leer qué se va a probar y con
qué criterio. Están fijados antes de ver resultados:

- [H3 (ML sobre el carry)](../estrategias/01-carry/pre-registro-h3.md);
- [H4 (carry entre exchanges)](../estrategias/01-carry/pre-registro-h4.md);
- [Momentum transversal](../estrategias/03-momentum-transversal/pre-registro.md);
- [Tendencia](../estrategias/02-tendencia/pre-registro.md).

Si quieres cambiar algo, **dilo antes de la primera ejecución**: después ya cuenta como una
enmienda con ensayos nuevos en N.

## Lo que no necesita nada tuyo

- **Releases a `main`:** solo cuando tú lo pidas. Hay un motivo para pedir uno pronto: GitHub
  ejecuta los jobs programados solo desde `main`. El job semanal de mutation testing (PQ-99) no
  correrá hasta el próximo release.
- **La VM de Oracle:** sigue el plan A (reintentar A1) y el plan B (créditos de estudiante); es
  carril de Claude B ([runbook](../runbooks/oracle-cloud.md)).
- **El resto de los tickets del sprint:** los agentes siguen avanzándolos y te avisan solo cuando
  necesitan algo de esta lista.
