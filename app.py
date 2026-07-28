import streamlit as st
import datetime
import math
import pandas as pd
from supabase import create_client, Client
import extra_streamlit_components as stx

# Configuración de página
st.set_page_config(page_title="Sistema Predictivo de Pedidos PJ", layout="wide")

# Instanciar el Cookie Manager sin caché para evitar advertencias de widgets
cookie_manager = stx.CookieManager()


# ================= SEGURIDAD (LOGIN PERSISTENTE) =================
def check_password():
    """Retorna True si el usuario tiene la cookie correcta o ingresa la clave."""
    # Leer la cookie (necesita estar arriba para que se lea al cargar)
    auth_status = cookie_manager.get(cookie="auth_status")
    
    if auth_status == "logged_in":
        return True

    def password_entered():
        if st.session_state.get("password", "") == st.secrets["APP_PASSWORD"]:
            # Guardar la cookie por 30 días
            cookie_manager.set("auth_status", "logged_in", expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
            st.session_state["password_correct"] = True
        else:
            st.session_state["password_correct"] = False

    st.markdown("<h3 style='text-align: center;'>🔒 Acceso Restringido</h3>", unsafe_allow_html=True)
    st.text_input("Introduce tu Contraseña Maestra", type="password", on_change=password_entered, key="password")
    
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("Contraseña incorrecta")
        
    return False

if not check_password():
    st.stop()  # Detiene la ejecución de la app si no está logueado

# ================= CONEXIÓN A SUPABASE =================
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error("Error al conectar a Supabase. Verifica tus Secretos.")
    st.stop()

# Título Principal
st.title("🍕 Sistema Predictivo de Pedidos - Papa John's")
st.markdown("---")

# ----------------- SIDEBAR (Gestión de Insumos) -----------------
st.sidebar.header("📦 Gestión de Insumos")
with st.sidebar.expander("➕ Añadir Nuevo Producto"):
    with st.form("form_nuevo_producto"):
        nuevo_nombre = st.text_input("Nombre del Insumo")
        nueva_categoria = st.selectbox("Categoría", ["Vegetales", "Gaseosas", "Perecibles", "Cajas"])
        nueva_cap_max = st.number_input("Capacidad Máxima (Unidades)", min_value=1.0, value=100.0, step=1.0)
        nuevo_uni_paq = st.number_input("Unidades por Paquete", min_value=1.0, value=1.0, step=1.0)
        
        if st.form_submit_button("Guardar Producto"):
            if nuevo_nombre.strip() == "":
                st.error("El nombre no puede estar vacío.")
            else:
                try:
                    data, count = supabase.table("productos").insert({
                        "nombre": nuevo_nombre,
                        "categoria": nueva_categoria,
                        "capacidad_maxima": nueva_cap_max,
                        "unidades_por_paquete": nuevo_uni_paq
                    }).execute()
                    st.success(f"Producto '{nuevo_nombre}' agregado a la nube.")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

st.sidebar.markdown("---")
st.sidebar.header("🗓️ Configuración de Pedido")
dia_pedido = st.sidebar.selectbox("Día de Pedido Actual", ["Lunes", "Miércoles", "Viernes"])

if dia_pedido == "Lunes":
    dias_gap = 2
    descripcion_gap = "Llega el Miércoles. Gap de 2 días (Lunes y Martes - Regulares)."
elif dia_pedido == "Miércoles":
    dias_gap = 2
    descripcion_gap = "Llega el Viernes. Gap de 2 días (Miércoles y Jueves - Regulares)."
else: # Viernes
    dias_gap = 3
    descripcion_gap = "Llega el Lunes. Gap de 3 días (Viernes, Sábado y Domingo - Fuertes)."

st.sidebar.info(descripcion_gap)

st.sidebar.markdown("---")
if st.sidebar.button("🚪 Cerrar Sesión"):
    cookie_manager.delete("auth_status")
    st.session_state.clear()
    st.rerun()


# Cargar productos disponibles desde la nube
try:
    response = supabase.table("productos").select("*").execute()
    df_productos = pd.DataFrame(response.data)
except Exception as e:
    st.error("No se pudieron cargar los productos de la nube.")
    df_productos = pd.DataFrame()

# ----------------- PESTAÑAS -----------------
tab1, tab2 = st.tabs(["📝 Realizar Pedido", "📈 Dashboard Analítico"])

with tab1:
    if df_productos.empty:
        st.warning("⚠️ No hay productos registrados en la base de datos.")
    else:
        # Selector Dinámico
        st.subheader("Selección de Producto")
        producto_seleccionado = st.selectbox("Elige el insumo a calcular", df_productos['nombre'].tolist())
        
        # Obtener datos del producto seleccionado
        prod_data = df_productos[df_productos['nombre'] == producto_seleccionado].iloc[0]
        CAPACIDAD_MAXIMA = prod_data['capacidad_maxima']
        UNIDADES_POR_PAQUETE = prod_data['unidades_por_paquete']
        CATEGORIA = prod_data['categoria']
        
        st.markdown(f"**Categoría:** `{CATEGORIA}` | **Capacidad Máx:** `{CAPACIDAD_MAXIMA}` | **Unidades/Paquete:** `{UNIDADES_POR_PAQUETE}`")
        
        # Memoria Predictiva (Historial)
        valor_defecto_consumo = 100.0
        try:
            res_historial = supabase.table("historial_pedidos").select("consumo_quincenal").eq("producto_nombre", producto_seleccionado).execute()
            if res_historial.data and len(res_historial.data) > 0:
                avg_consumo = sum([item['consumo_quincenal'] for item in res_historial.data]) / len(res_historial.data)
                valor_defecto_consumo = round(avg_consumo, 2)
                st.info(f"🧠 **Asistente Inteligente:** Basado en el historial, el consumo promedio quincenal sugerido es **{valor_defecto_consumo}**.")
        except Exception as e:
            pass
        
        # Entradas
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Entradas del Usuario")
            consumo_14_dias = st.number_input("Consumo de 14 días (Quincenal)", min_value=0.0, value=float(valor_defecto_consumo), step=1.0)
            stock_actual = st.number_input("Stock Actual Físico (Unidades)", min_value=0.0, value=0.0, step=1.0)
            mercaderia_transito = st.number_input("Mercadería en Tránsito (Llega hoy)", min_value=0.0, value=0.0, step=1.0)
            
        with col2:
            st.subheader("Datos del Producto")
            col2_1, col2_2 = st.columns(2)
            with col2_1:
                st.metric(label="Capacidad Máxima", value=f"{CAPACIDAD_MAXIMA} unid.")
            with col2_2:
                st.metric(label="Unidades por Paquete", value=f"{UNIDADES_POR_PAQUETE} unid.")
        
        # Cálculos
        if st.button("Calcular Pedido Ponderado y Guardar", type="primary"):
            consumo_semanal = consumo_14_dias / 2.0
            valor_base_diario = consumo_semanal / 10.0
            
            consumo_diario_regular = valor_base_diario * 1.0
            consumo_diario_fuerte = valor_base_diario * 2.0
            
            if dia_pedido == "Lunes" or dia_pedido == "Miércoles":
                gasto_proyectado = 2 * consumo_diario_regular
            else: # Viernes
                gasto_proyectado = 3 * consumo_diario_fuerte
                
            stock_total_hoy = stock_actual + mercaderia_transito
            stock_al_recibir = max(0, stock_total_hoy - gasto_proyectado)
            unidades_a_pedir = max(0, CAPACIDAD_MAXIMA - stock_al_recibir)
            paquetes_a_pedir = round(unidades_a_pedir / UNIDADES_POR_PAQUETE)
            
            # Guardar en BD Supabase
            try:
                supabase.table("historial_pedidos").insert({
                    "dia_pedido": dia_pedido,
                    "producto_nombre": producto_seleccionado,
                    "consumo_quincenal": consumo_14_dias,
                    "stock_actual": stock_total_hoy,
                    "dias_gap": dias_gap,
                    "paquetes_a_pedir": paquetes_a_pedir
                }).execute()
                
                st.success("✅ Pedido calculado y respaldado de forma segura en la Nube.")
                
                # Resultado
                st.markdown(
                    f"""
                    <div style="text-align: center; padding: 20px; border-radius: 10px; background-color: #f0f2f6;">
                        <h1 style="color: #1e3d59; font-size: 3rem; margin-bottom: 0;">{paquetes_a_pedir}</h1>
                        <h3 style="color: #4a4a4a; margin-top: 0;">Paquetes a Pedir de {producto_seleccionado}</h3>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                with st.expander("Ver desglose del cálculo"):
                    st.write(f"- **Consumo Quincenal (14 días):** {consumo_14_dias:.2f}")
                    st.write(f"- **Stock Físico Actual:** {stock_actual:.2f}")
                    if mercaderia_transito > 0:
                        st.write(f"- **Mercadería en Tránsito:** {mercaderia_transito:.2f}")
                    st.write(f"- **Stock Total Hoy:** {stock_total_hoy:.2f}")
                    st.write(f"- **Gasto Proyectado Total (Gap):** {gasto_proyectado:.2f}")
                    st.write(f"- **Stock Proyectado al Recibir (Total Hoy - Gap):** {stock_al_recibir:.2f}")
                    st.write(f"- **Unidades a Pedir:** {unidades_a_pedir:.2f}")
                    st.write(f"- **Paquetes:** {paquetes_a_pedir}")
            except Exception as e:
                st.error(f"Error al guardar en la base de datos: {e}")

with tab2:
    st.header("📈 Dashboard Analítico y Eficiencia")
    
    try:
        res_dash = supabase.table("historial_pedidos").select("*").execute()
        df_historial = pd.DataFrame(res_dash.data)
    except Exception as e:
        df_historial = pd.DataFrame()
        
    if df_historial.empty:
        st.info("Aún no hay suficientes datos para mostrar en el Dashboard. Guarda algunos pedidos primero.")
    else:
        # Asegurar tipo fecha
        df_historial['fecha_registro'] = pd.to_datetime(df_historial['fecha_registro'])
        df_historial['Mes'] = df_historial['fecha_registro'].dt.to_period('M').astype(str)
        
        # Filtro de producto
        prod_filtro = st.selectbox("Selecciona producto para analizar", ["Todos"] + df_productos['nombre'].tolist())
        
        if prod_filtro != "Todos":
            df_filtrado = df_historial[df_historial['producto_nombre'] == prod_filtro]
            capacidad_max_filtro = df_productos[df_productos['nombre'] == prod_filtro].iloc[0]['capacidad_maxima']
        else:
            df_filtrado = df_historial
            capacidad_max_filtro = None
            
        if df_filtrado.empty:
            st.warning("No hay pedidos de este producto.")
        else:
            st.subheader("Evolución de Pedidos (Paquetes)")
            df_tendencia = df_filtrado.groupby(df_filtrado['fecha_registro'].dt.date)['paquetes_a_pedir'].sum()
            st.line_chart(df_tendencia)
            
            meses_agrupados = df_filtrado.groupby('Mes')['paquetes_a_pedir'].sum()
            if not meses_agrupados.empty:
                mes_pico = meses_agrupados.idxmax()
                val_pico = meses_agrupados.max()
                st.info(f"🏆 **Mes con mayor demanda:** {mes_pico} ({val_pico} paquetes)")
            
            # Auditoría de Ineficiencia ("Pedidos en vano")
            st.subheader("⚠️ Auditoría de Pedidos Ineficientes")
            st.write("Identifica pedidos realizados cuando el stock en almacén aún era muy alto (dinero inmovilizado).")
            
            if prod_filtro != "Todos":
                umbral_ineficiencia = capacidad_max_filtro * 0.70
                df_ineficientes = df_filtrado[df_filtrado['stock_actual'] >= umbral_ineficiencia]
                
                if df_ineficientes.empty:
                    st.success("✅ No se detectaron pedidos con exceso de stock para este producto.")
                else:
                    st.error(f"Se encontraron {len(df_ineficientes)} registros donde el stock era >= 70% de la capacidad máxima.")
                    st.dataframe(df_ineficientes[['fecha_registro', 'dia_pedido', 'stock_actual', 'paquetes_a_pedir']])
            else:
                st.write("Por favor, selecciona un producto específico arriba para habilitar el análisis de ineficiencia.")
