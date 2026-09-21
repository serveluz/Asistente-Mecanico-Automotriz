import os
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from fpdf import FPDF
import datetime

# Cargar variables de entorno
load_dotenv(".env")
load_dotenv("Principal.env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("⚠️ Falta configurar SUPABASE_URL y SUPABASE_KEY en el archivo .env o Principal.env")
    st.stop()

# Inicializar clientes
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

st.set_page_config(page_title="Taller Mecánico - George", layout="wide", page_icon="🔧")

st.title("🔧 Sistema Integral de Gestión Automotriz")

# Menú lateral completo
menu = st.sidebar.radio("Navegación", [
    "Clientes y Vehículos", 
    "Tarjetas de Trabajo e Inspección", 
    "Inventario y Refacciones",
    "Estimaciones y Facturas (PDF)",
    "Citas y Recordatorios",
    "Diagnóstico OBD2 (IA)",
    "Proveedores e Informes",
    "Papelera de Reciclaje (7 días)"
])

# Cargar datos base
try:
    all_clients_res = supabase.table("clients").select("*").execute()
    all_clients = all_clients_res.data if all_clients_res.data else []
    active_clients = [c for c in all_clients if c.get("deleted_at") is None]

    all_vehs_res = supabase.table("vehicles").select("*").execute()
    all_vehs = all_vehs_res.data if all_vehs_res.data else []
    active_vehs = [v for v in all_vehs if v.get("deleted_at") is None]
except Exception as e:
    st.error(f"Error consultando base de datos: {e}")
    active_clients, active_vehs = [], []

# ----------------------------------------------------
# 1. CLIENTES Y VEHÍCULOS
# ----------------------------------------------------
if menu == "Clientes y Vehículos":
    st.header("👤 Registro de Clientes y Vehículos")
    col_client, col_veh = st.columns(2)
    
    with col_client:
        with st.form("add_client_form", clear_on_submit=True):
            st.subheader("Nuevo Cliente")
            name = st.text_input("Nombre completo *")
            phone = st.text_input("Teléfono")
            email = st.text_input("Correo electrónico")
            submitted_client = st.form_submit_button("Guardar Cliente")
            
            if submitted_client and name:
                supabase.table("clients").insert({"full_name": name, "phone": phone, "email": email}).execute()
                st.success(f"Cliente '{name}' registrado.")
                st.rerun()

    with col_veh:
        st.subheader("Nuevo Vehículo")
        if active_clients:
            client_options = {c["full_name"]: c["id"] for c in active_clients}
            selected_client_name = st.selectbox("Seleccionar Dueño", list(client_options.keys()))
            
            with st.form("add_vehicle_form", clear_on_submit=True):
                make = st.text_input("Marca")
                model = st.text_input("Modelo")
                year = st.number_input("Año", min_value=1900, max_value=2030, value=2020)
                plates = st.text_input("Placas")
                vin = st.text_input("VIN / No. Serie")
                submitted_veh = st.form_submit_button("Guardar Vehículo")
                
                if submitted_veh and make and model:
                    client_id = client_options[selected_client_name]
                    supabase.table("vehicles").insert({
                        "client_id": client_id, "make": make, "model": model,
                        "year": year, "license_plate": plates, "vin": vin
                    }).execute()
                    st.success(f"Vehículo '{make} {model}' asignado a {selected_client_name}.")
                    st.rerun()
        else:
            st.info("Registra un cliente primero.")

    st.divider()
    st.subheader("📋 Directorio Activo")
    for c in active_clients:
        with st.expander(f"👤 {c['full_name']} | 📞 {c.get('phone', 'N/A')}"):
            vehs = [v for v in active_vehs if v.get("client_id") == c["id"]]
            for v in vehs:
                st.write(f"- 🚗 **{v['make']} {v['model']} ({v['year']})** | Placas: `{v.get('license_plate', 'S/N')}`")
            if st.button("🗑️ Mover Cliente a Papelera", key=f"del_{c['id']}"):
                supabase.table("clients").update({"deleted_at": "now()"}).eq("id", c["id"]).execute()
                st.rerun()

# ----------------------------------------------------
# 2. TARJETAS DE TRABAJO E INSPECCIÓN
# ----------------------------------------------------
elif menu == "Tarjetas de Trabajo e Inspección":
    st.header("📋 Orden de Trabajo e Inspección")
    if active_vehs:
        col_wo1, col_wo2 = st.columns(2)
        with col_wo1:
            veh_options = {f"{v['make']} {v['model']} ({v.get('license_plate', 'S/N')})": v for v in active_vehs}
            selected_veh_str = st.selectbox("Selecciona Vehículo", list(veh_options.keys()))
            selected_veh = veh_options[selected_veh_str]
        with col_wo2:
            description = st.text_area("Descripción del servicio / Falla")
            total_amount = st.number_input("Monto Estimado ($)", min_value=0.0, step=50.0)

        uploaded_file = st.file_uploader("Fotografía de inspección de daños", type=["jpg", "png"])
        
        if st.button("🚀 Guardar Orden de Trabajo"):
            wo_res = supabase.table("work_orders").insert({
                "client_id": selected_veh["client_id"], "vehicle_id": selected_veh["id"],
                "description": description, "total_amount": total_amount, "status": "in_progress"
            }).execute()
            wo_id = wo_res.data[0]["id"] if wo_res.data else None
            
            img_url = None
            if uploaded_file and wo_id:
                file_bytes = uploaded_file.read()
                file_path = f"inspections/{wo_id}_{uploaded_file.name}"
                try:
                    supabase.storage.from_("inspection-images").upload(file_path, file_bytes, {"content-type": uploaded_file.type})
                    img_url = supabase.storage.from_("inspection-images").get_public_url(file_path)
                except Exception as storage_err:
                    st.warning(f"Detalle al subir foto: {storage_err}")

            if wo_id:
                supabase.table("inspections").insert({
                    "work_order_id": wo_id, "damage_report": description,
                    "image_urls": [img_url] if img_url else []
                }).execute()
            st.success("¡Tarjeta creada!")
            st.rerun()

    st.divider()
    st.subheader("🛠️ Trabajos en Progreso")
    wo_res = supabase.table("work_orders").select("*").is_("deleted_at", None).execute()
    for wo in (wo_res.data or []):
        st.write(f"**Orden #{wo['id'][:8]}** | Estado: `{wo['status']}` | Total: ${wo.get('total_amount', 0)}")
        if st.button("🗑️ Eliminar Orden", key=f"del_wo_{wo['id']}"):
            supabase.table("work_orders").update({"deleted_at": "now()"}).eq("id", wo["id"]).execute()
            st.rerun()

# ----------------------------------------------------
# 3. INVENTARIO Y REFACCIONES
# ----------------------------------------------------
elif menu == "Inventario y Refacciones":
    st.header("📦 Gestión de Inventario y Refacciones")
    with st.form("add_item"):
        col1, col2, col3 = st.columns(3)
        item_name = col1.text_input("Nombre de la pieza / neumático")
        sku = col2.text_input("Código SKU / Parte")
        category = col3.selectbox("Categoría", ["Neumáticos", "Aceites y Fluidos", "Frenos", "Suspensión", "Filtros", "General"])
        
        qty = col1.number_input("Cantidad en Stock", min_value=0, value=10)
        cost = col2.number_input("Costo Compra ($)", min_value=0.0, value=100.0)
        price = col3.number_input("Precio Venta ($)", min_value=0.0, value=180.0)
        
        if st.form_submit_button("Añadir al Inventario") and item_name:
            supabase.table("inventory").insert({
                "item_name": item_name, "sku_code": sku, "category": category,
                "quantity_in_stock": qty, "cost_price": cost, "unit_price": price
            }).execute()
            st.success(f"'{item_name}' añadido al inventario.")
            st.rerun()

    st.divider()
    st.subheader("📊 Stock Actual")
    inv_res = supabase.table("inventory").select("*").is_("deleted_at", None).execute()
    for item in (inv_res.data or []):
        alert = "⚠️ ¡STOCK BAJO!" if item["quantity_in_stock"] <= item.get("min_stock_alert", 5) else "✅ OK"
        st.write(f"**{item['item_name']}** (`{item.get('sku_code', 'N/A')}`) | Categoría: {item['category']} | Cantidad: **{item['quantity_in_stock']}** unidades | Estado: {alert}")

# ----------------------------------------------------
# 4. ESTIMACIONES Y FACTURAS (PDF)
# ----------------------------------------------------
elif menu == "Estimaciones y Facturas (PDF)":
    st.header("📄 Generador de Presupuestos y Facturas en PDF")
    
    col_f1, col_f2 = st.columns(2)
    client_name = col_f1.text_input("Nombre del Cliente", value="Cliente Ejemplo")
    vehicle_info = col_f2.text_input("Vehículo", value="Nissan Versa 2021")
    doc_type = col_f1.selectbox("Tipo de Documento", ["Presupuesto / Estimación", "Factura de Servicio"])
    
    concept = st.text_input("Concepto / Trabajo realizado", value="Alineación, balanceo y cambio de balatas delanteras")
    amount = st.number_input("Monto Total ($)", min_value=0.0, value=1500.0)
    
    def generate_pdf(client, veh, dtype, desc, total):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 16)
        pdf.cell(0, 10, f"TALLER MECÁNICO - {dtype.upper()}", ln=True, align='C')
        pdf.ln(10)
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 8, f"Fecha: {datetime.date.today()}", ln=True)
        pdf.cell(0, 8, f"Cliente: {client}", ln=True)
        pdf.cell(0, 8, f"Vehiculo: {veh}", ln=True)
        pdf.ln(10)
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(0, 8, "Detalle del Servicio:", ln=True)
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 8, desc)
        pdf.ln(10)
        pdf.set_font("Helvetica", 'B', 14)
        pdf.cell(0, 10, f"TOTAL: ${total:.2f} MXN", ln=True, align='R')
        return pdf.output()

    if st.button("📄 Generar y Descargar PDF"):
        pdf_bytes = generate_pdf(client_name, vehicle_info, doc_type, concept, amount)
        st.download_button(
            label="⬇️ Descargar Documento PDF",
            data=bytes(pdf_bytes),
            file_name=f"{doc_type.replace(' ', '_')}_{client_name}.pdf",
            mime="application/pdf"
        )

# ----------------------------------------------------
# 5. CITAS Y RECORDATORIOS
# ----------------------------------------------------
elif menu == "Citas y Recordatorios":
    st.header("📅 Agenda de Citas y Recordatorios Inteligentes")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.subheader("Programar Cita")
        if active_clients:
            c_name = st.selectbox("Cliente", [c["full_name"] for c in active_clients])
            service = st.text_input("Servicio a realizar", value="Mantenimiento preventivo 10,000 km")
            date_app = st.date_input("Fecha de la cita")
            if st.button("Agendar Cita"):
                st.success(f"Cita agendada para {c_name} el día {date_app}.")

    with col_c2:
        st.subheader("🤖 Generar Recordatorio con IA (WhatsApp/Email)")
        if st.button("Redactar Mensaje de Recordatorio"):
            if ai_client:
                prompt = "Redacta un mensaje amable y profesional para WhatsApp recordando a un cliente que su auto ya necesita servicio de mantenimiento preventivo después de 6 meses."
                response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                st.text_area("Mensaje listo para enviar:", value=response.text, height=180)

# ----------------------------------------------------
# 6. DIAGNÓSTICO OBD2 (IA)
# ----------------------------------------------------
elif menu == "Diagnóstico OBD2 (IA)":
    st.header("🤖 Asistente de Diagnóstico OBD2 con IA")
    dtc_code = st.text_input("Código de Falla OBD2 (Ej. P0300):", placeholder="P0300")
    vehicle_info = st.text_input("Auto (Ej. Ford Mustang 2015 5.0L):", placeholder="Toyota Corolla 2018")
    
    if st.button("Generar Diagnóstico") and dtc_code and ai_client:
        with st.spinner("Analizando con Gemini..."):
            prompt = f"Actúa como mecánico máster. Explica el código OBD2 '{dtc_code}' en '{vehicle_info}'. Incluye causas, reparación y explicación clara para el cliente."
            response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            st.markdown("### 📋 Informe de Reparación")
            st.write(response.text)

# ----------------------------------------------------
# 7. PROVEEDORES E INFORMES
# ----------------------------------------------------
elif menu == "Proveedores e Informes":
    st.header("📈 Rendimiento del Negocio y Proveedores")
    st.subheader("Proveedores Registrados")
    with st.form("add_supplier"):
        c1, c2, c3 = st.columns(3)
        comp = c1.text_input("Empresa / Nombre")
        cont = c2.text_input("Contacto / Teléfono")
        item_sup = c3.text_input("Tipo de refacciones")
        if st.form_submit_button("Guardar Proveedor") and comp:
            supabase.table("suppliers").insert({"company_name": comp, "contact_name": cont, "phone": item_sup}).execute()
            st.success("Proveedor añadido.")
            st.rerun()
            
    sups = supabase.table("suppliers").select("*").execute().data or []
    for s in sups:
        st.write(f"- 🏢 **{s['company_name']}** | Contacto: {s.get('contact_name', 'N/A')}")

# ----------------------------------------------------
# 8. PAPELERA DE RECICLAJE
# ----------------------------------------------------
elif menu == "Papelera de Reciclaje (7 días)":
    st.header("🗑️ Papelera de Reciclaje (Restauración de 7 días)")
    deleted_clients = [c for c in all_clients if c.get("deleted_at") is not None]
    if deleted_clients:
        for dc in deleted_clients:
            col1, col2 = st.columns([4, 1])
            col1.write(f"**{dc['full_name']}** (Eliminado: {str(dc.get('deleted_at'))[:10]})")
            if col2.button("🔄 Restaurar", key=f"rest_{dc['id']}"):
                supabase.table("clients").update({"deleted_at": None}).eq("id", dc["id"]).execute()
                st.rerun()
    else:
        st.info("La papelera está vacía.")