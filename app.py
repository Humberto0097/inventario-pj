import streamlit as st
import datetime
import pandas as pd
from supabase import create_client, Client
import extra_streamlit_components as stx
import re

# Configuración de página
st.set_page_config(page_title="ZailasPH - Gestión de Inventarios", layout="wide")

# Instanciar el Cookie Manager sin caché para evitar advertencias de widgets
cookie_manager = stx.CookieManager()

# ================= SEGURIDAD (LOGIN PERSISTENTE) =================
def check_password():
    auth_status = cookie_manager.get(cookie="auth_status")
    if auth_status == "logged_in":
        return True

    def password_entered():
        if st.session_state.get("password", "") == st.secrets["APP_PASSWORD"]:
            cookie_manager.set("auth_status", "logged_in", expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
            st.session_state["password_correct"] = True
        else:
            st.session_state["password_correct"] = False

    st.markdown("<h3 style='text-align: center;'>🔒 Acceso Restringido - ZailasPH</h3>", unsafe_allow_html=True)
    st.text_input("Introduce tu Contraseña Maestra", type="password", on_change=password_entered, key="password")
    
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("Contraseña incorrecta")
        
    return False

if not check_password():
    st.stop()

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

# ================= MENÚ LATERAL =================
st.sidebar.title("🍕 ZailasPH")
st.sidebar.markdown("---")
menu = st.sidebar.radio("Navegación", [
    "🏷️ Calculadora de Fechados",
    "📦 Catálogo Maestro",
    "📊 Pedidos DRP (Próximamente)",
    "📉 Varianza (Próximamente)"
])

st.sidebar.markdown("---")
if st.sidebar.button("🚪 Cerrar Sesión"):
    cookie_manager.delete("auth_status")
    st.session_state.clear()
    st.rerun()

# ================= FUNCIONES AUXILIARES =================
def calcular_vencimiento(regla_texto):
    """Parsea el texto de vida útil (ej. '10h', '7', '11:59') y calcula la fecha/hora de vencimiento."""
    if not regla_texto or regla_texto.strip() == "" or regla_texto.lower() == "se":
        return None
    
    ahora = datetime.datetime.now()
    regla = regla_texto.strip().lower()
    
    # Regla de fin de día (11:59)
    if "11:59" in regla:
        vencimiento = ahora.replace(hour=23, minute=59, second=59)
        if vencimiento < ahora:
            vencimiento += datetime.timedelta(days=1)
        return vencimiento
        
    # Regla de horas (ej. '10h', '12h')
    match_horas = re.search(r'(\d+)\s*h', regla)
    if match_horas:
        horas = int(match_horas.group(1))
        return ahora + datetime.timedelta(hours=horas)
        
    # Regla de minutos (ej. '30m')
    match_min = re.search(r'(\d+)\s*m', regla)
    if match_min:
        minutos = int(match_min.group(1))
        return ahora + datetime.timedelta(minutes=minutos)
        
    # Regla de días (solo números, ej. '7', '14')
    match_dias = re.search(r'^(\d+)$', regla)
    if match_dias:
        dias = int(match_dias.group(1))
        vencimiento = ahora + datetime.timedelta(days=dias)
        return vencimiento.replace(hour=23, minute=59, second=59)
        
    return None

# ================= VISTAS =================

if menu == "🏷️ Calculadora de Fechados":
    st.title("🏷️ Fechados y Vida Útil (PEPS)")
    st.markdown("Calcula rápidamente qué fecha y hora debes poner en la etiqueta al abrir o preparar un insumo.")
    
    # Cargar catálogo
    res = supabase.table("productos_maestro").select("*").execute()
    df = pd.DataFrame(res.data)
    
    if df.empty:
        st.warning("⚠️ No hay productos en el Catálogo Maestro. Ve a la pestaña 'Catálogo Maestro' para agregar algunos.")
    else:
        categorias = ["Todos"] + df['categoria'].unique().tolist()
        cat_seleccionada = st.selectbox("Filtrar por Categoría", categorias)
        
        if cat_seleccionada != "Todos":
            df = df[df['categoria'] == cat_seleccionada]
            
        producto_nombre = st.selectbox("Selecciona el Insumo / Prep", df['descripcion'].tolist())
        
        prod_data = df[df['descripcion'] == producto_nombre].iloc[0]
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**Vida Útil (Preparación/Abierto):** {prod_data['vida_preparacion']}")
            venc_prep = calcular_vencimiento(prod_data['vida_preparacion'])
            if venc_prep:
                st.success(f"### Etiquetar para:\n## {venc_prep.strftime('%d/%m/%Y a las %I:%M %p')}")
            else:
                st.markdown("*No hay regla calculable para preparación. Revisar empaque.*")
                
        with col2:
            st.warning(f"**Vida Útil (Línea de Producción):** {prod_data['vida_linea']}")
            venc_linea = calcular_vencimiento(prod_data['vida_linea'])
            if venc_linea:
                st.success(f"### Etiquetar para:\n## {venc_linea.strftime('%d/%m/%Y a las %I:%M %p')}")
            else:
                st.markdown("*No hay regla calculable para línea.*")

elif menu == "📦 Catálogo Maestro":
    st.title("📦 Gestión del Catálogo Maestro")
    st.markdown("Añade los insumos con sus tiempos de vida útil (R, P, L) según tus tablas manuales.")
    
    with st.expander("➕ Añadir Nuevo Insumo / Prep", expanded=True):
        with st.form("form_catalogo"):
            col1, col2, col3 = st.columns(3)
            with col1:
                cod_sap = st.text_input("Código SAP (Opcional)")
            with col2:
                categoria = st.selectbox("Categoría", ["Carnicos", "Quesos", "Salsas", "Vegetales", "Preps", "Limpieza", "Otros", "Masas", "Cajas", "Gaseosas"])
            with col3:
                desc = st.text_input("Descripción del Producto")
                
            st.markdown("#### Tiempos de Vida Útil")
            c1, c2, c3 = st.columns(3)
            with c1:
                vida_r = st.text_input("Recepción (R) - Ej: '14', 'Se'")
            with c2:
                vida_p = st.text_input("Preparación (P) - Ej: '10h', '7'")
            with c3:
                vida_l = st.text_input("Línea (L) - Ej: '11:59', '1'")
                
            paquete_kg = st.number_input("Factor de Conversión (Kg por caja/paquete para SAP)", min_value=0.0, value=1.0, step=0.1)
            
            if st.form_submit_button("Guardar en Catálogo"):
                if desc.strip() == "":
                    st.error("La descripción es obligatoria.")
                else:
                    try:
                        supabase.table("productos_maestro").insert({
                            "codigo_sap": cod_sap,
                            "categoria": categoria,
                            "descripcion": desc,
                            "vida_recepcion": vida_r,
                            "vida_preparacion": vida_p,
                            "vida_linea": vida_l,
                            "paquete_kg": paquete_kg
                        }).execute()
                        st.success(f"Insumo '{desc}' guardado correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                        
    # Mostrar catálogo actual
    st.subheader("Catálogo Actual en Supabase")
    res = supabase.table("productos_maestro").select("*").execute()
    if res.data:
        st.dataframe(pd.DataFrame(res.data), use_container_width=True)
    else:
        st.info("Catálogo vacío.")

else:
    st.title("🚧 Módulo en Construcción")
    st.markdown("Estamos construyendo esta sección (Fase 2). ¡Pronto ZailasPH calculará los pedidos y varianzas aquí!")
