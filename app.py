import streamlit as st
import datetime
import pandas as pd
from supabase import create_client, Client
import extra_streamlit_components as stx
import re
from PIL import Image
import pytesseract

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
    "📊 Pedidos DRP",
    "📉 Varianza de Consumo",
    "📸 Lector Visual (OCR)"
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
        df_maestro = pd.DataFrame(res.data)
        st.dataframe(df_maestro, use_container_width=True)
        
        st.markdown("---")
        st.subheader("🛠️ Editar o Eliminar Insumo")
        insumo_a_modificar = st.selectbox("Selecciona un insumo para modificar/eliminar", df_maestro['descripcion'].tolist())
        insumo_data = df_maestro[df_maestro['descripcion'] == insumo_a_modificar].iloc[0]
        insumo_id = int(insumo_data['id'])
        
        col_ed1, col_ed2 = st.columns(2)
        with col_ed1:
            if st.button("🗑️ Eliminar Insumo", type="primary", use_container_width=True):
                try:
                    supabase.table("productos_maestro").delete().eq("id", insumo_id).execute()
                    st.success(f"Insumo '{insumo_a_modificar}' eliminado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al eliminar: {e}")
                    
        with col_ed2:
            with st.expander("✏️ Editar Insumo"):
                with st.form("form_editar"):
                    e_cod = st.text_input("Código SAP", value=insumo_data.get('codigo_sap', ''))
                    # Buscar el índice seguro de la categoría
                    lista_cat = ["Carnicos", "Quesos", "Salsas", "Vegetales", "Preps", "Limpieza", "Otros", "Masas", "Cajas", "Gaseosas"]
                    try:
                        idx_cat = lista_cat.index(insumo_data['categoria'])
                    except:
                        idx_cat = 0
                        
                    e_cat = st.selectbox("Categoría", lista_cat, index=idx_cat)
                    e_r = st.text_input("Recepción (R)", value=insumo_data.get('vida_recepcion', ''))
                    e_p = st.text_input("Preparación (P)", value=insumo_data.get('vida_preparacion', ''))
                    e_l = st.text_input("Línea (L)", value=insumo_data.get('vida_linea', ''))
                    
                    val_kg = float(insumo_data.get('paquete_kg', 1.0))
                    if pd.isna(val_kg): val_kg = 1.0
                    e_kg = st.number_input("Factor Kg", value=val_kg)
                    
                    if st.form_submit_button("💾 Guardar Cambios"):
                        try:
                            supabase.table("productos_maestro").update({
                                "codigo_sap": e_cod,
                                "categoria": e_cat,
                                "vida_recepcion": e_r,
                                "vida_preparacion": e_p,
                                "vida_linea": e_l,
                                "paquete_kg": e_kg
                            }).eq("id", insumo_id).execute()
                            st.success("¡Insumo actualizado exitosamente!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al actualizar: {e}")

    else:
        st.info("Catálogo vacío.")

elif menu == "📊 Pedidos DRP":
    st.title("📊 Módulo de Pedidos (DRP Inteligente)")
    st.markdown("Copia y pega la data de SAP. ZailasPH calculará el pedido sugerido al instante.")
    
    # 1. Cargar productos
    res = supabase.table("productos_maestro").select("*").execute()
    df_maestro = pd.DataFrame(res.data)
    
    if df_maestro.empty:
        st.warning("⚠️ El Catálogo Maestro está vacío. Añade productos primero.")
    else:
        categorias_disp = df_maestro['categoria'].unique().tolist()
        cat_ped = st.selectbox("Categoría a Pedir", categorias_disp)
        
        df_cat = df_maestro[df_maestro['categoria'] == cat_ped].copy()
        
        st.subheader("Configuración de Días")
        dias_a_cubrir = st.number_input("Días de Inventario a Cubrir (Días hasta el PRÓXIMO ingreso después de este)", min_value=1.0, value=3.0, step=0.5)
        
        st.markdown("### Tabla DRP Editable")
        st.caption("📝 Tip: Puedes copiar desde tu Excel y pegar directamente en las columnas 'Consumo Diario', 'Stock SAP' y 'Tránsito'.")
        
        # Preparamos el dataframe para el editor
        df_editor = df_cat[['codigo_sap', 'descripcion', 'paquete_kg']].copy()
        df_editor['Consumo Diario Promedio'] = 0.0
        df_editor['Stock SAP'] = 0.0
        df_editor['Tránsito'] = 0.0
        
        # Editor interactivo
        edited_df = st.data_editor(
            df_editor,
            column_config={
                "codigo_sap": st.column_config.TextColumn("Cód. SAP", disabled=True),
                "descripcion": st.column_config.TextColumn("Insumo", disabled=True),
                "paquete_kg": st.column_config.NumberColumn("Factor Convert.", disabled=True),
                "Consumo Diario Promedio": st.column_config.NumberColumn("Consumo Diario Prom.", min_value=0.0, format="%.2f"),
                "Stock SAP": st.column_config.NumberColumn("Stock Actual SAP", min_value=0.0, format="%.2f"),
                "Tránsito": st.column_config.NumberColumn("Mercadería en Tránsito", min_value=0.0, format="%.2f"),
            },
            hide_index=True,
            use_container_width=True
        )
        
        st.markdown("---")
        st.subheader("📦 Resultado: Pedido Sugerido para ME51N")
        
        resultado_df = edited_df.copy()
        # Lógica: Lo que voy a gastar en los días a cubrir, menos lo que ya tengo (Stock + Transito)
        resultado_df['Pedido (Unidades)'] = (resultado_df['Consumo Diario Promedio'] * dias_a_cubrir) - (resultado_df['Stock SAP'] + resultado_df['Tránsito'])
        
        # Evitar números negativos
        resultado_df['Pedido (Unidades)'] = resultado_df['Pedido (Unidades)'].apply(lambda x: max(0, round(x, 2)))
        
        # Mostrar tabla final limpia
        st.dataframe(resultado_df[['codigo_sap', 'descripcion', 'Pedido (Unidades)']], use_container_width=True, hide_index=True)

elif menu == "📉 Varianza de Consumo":
    st.title("📉 Varianza de Consumo (MB51)")
    st.markdown("Pega aquí tu exportación de SAP (MB51) de los **últimos 28 días** para calcular tu Consumo Diario Promedio real.")
    
    st.info("💡 **Clases de movimiento consideradas:** Ajustes (701-702), Receta (951-952), Merma (957-958), Refrigerio (967-968) y Consumo Interno (975-976).")
    
    # Editor para pegar data de MB51
    df_mb51 = pd.DataFrame(columns=["Código SAP", "Insumo", "Clase Mov.", "Cantidad"])
    
    st.caption("📝 Tip: Selecciona las 4 columnas de tu Excel de SAP (Material, Texto, CmMv, Cantidad) y pégalas aquí:")
    edited_mb51 = st.data_editor(df_mb51, num_rows="dynamic", use_container_width=True)
    
    if st.button("🚀 Calcular Consumo Diario Promedio", type="primary"):
        if edited_mb51.empty:
            st.warning("Pega los datos primero.")
        else:
            try:
                # Filtrar solo los movimientos relevantes y convertir cantidades
                movs_validos = ['701', '702', '951', '952', '957', '958', '967', '968', '975', '976']
                
                # Asegurar que Clase Mov. es string
                edited_mb51['Clase Mov.'] = edited_mb51['Clase Mov.'].astype(str)
                # Convertir Cantidad a numérico
                edited_mb51['Cantidad'] = pd.to_numeric(edited_mb51['Cantidad'], errors='coerce').fillna(0)
                
                # Filtrar
                df_filtrado = edited_mb51[edited_mb51['Clase Mov.'].isin(movs_validos)]
                
                # Agrupar por Insumo
                resumen = df_filtrado.groupby(['Código SAP', 'Insumo'])['Cantidad'].sum().reset_index()
                
                # Dividir entre 28 días
                resumen['Consumo Total (28 días)'] = resumen['Cantidad'].abs() # En SAP algunas salidas son negativas
                resumen['Consumo Diario Promedio'] = (resumen['Consumo Total (28 días)'] / 28.0).round(2)
                
                st.success("✅ ¡Cálculo completado! Usa estos promedios en tu módulo de Pedidos DRP.")
                st.dataframe(resumen[['Código SAP', 'Insumo', 'Consumo Total (28 días)', 'Consumo Diario Promedio']], use_container_width=True, hide_index=True)
                
            except Exception as e:
                st.error(f"Error al calcular: Asegúrate de pegar los números correctamente. Detalle: {e}")

elif menu == "📸 Lector Visual (OCR)":
    st.title("📸 Lector de Imágenes (OCR)")
    st.markdown("Sube fotos de tus guías, facturas o pantallas de SAP para extraer el texto automáticamente usando IA.")
    
    st.info("💡 **Ideal para:** Pasar notas físicas a texto digital sin teclear.")
    
    uploaded_image = st.file_uploader("Sube una imagen (PNG, JPG)", type=["png", "jpg", "jpeg"])
    if uploaded_image is not None:
        try:
            image = Image.open(uploaded_image)
            st.image(image, caption="Imagen Subida", use_container_width=True)
            
            if st.button("🔍 Extraer Texto de la Imagen", type="primary"):
                with st.spinner("⏳ Leyendo imagen con Tesseract OCR... Esto puede tardar unos segundos."):
                    texto_extraido = pytesseract.image_to_string(image, lang="spa")
                    
                    if texto_extraido and texto_extraido.strip():
                        st.success("✅ ¡Texto extraído con éxito!")
                        st.text_area("Texto Encontrado:", value=texto_extraido, height=300)
                    else:
                        st.warning("⚠️ No se detectó texto legible en la imagen.")
        except Exception as e:
            st.error(f"Error procesando la imagen. Detalle: {e}")
            st.info("Nota técnica: Si estás probando esto localmente en Windows, necesitas tener instalado 'Tesseract OCR' en tu computadora. En la nube (Streamlit Cloud) ya hemos configurado 'packages.txt' para que funcione.")
