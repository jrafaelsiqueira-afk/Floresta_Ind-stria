import streamlit as st
from supabase import create_client, Client
from streamlit_drawable_canvas import st_canvas
from fpdf import FPDF
from pypdf import PdfWriter, PdfReader
from datetime import datetime, timedelta
from PIL import Image
import numpy as np
import pandas as pd
import io
import tempfile
import os
import unicodedata

# Configuração da página (DEVE SER A PRIMEIRA LINHA)
st.set_page_config(page_title="Florestal Operacional", layout="wide", page_icon="🌲")

# ---------------------------------------------------------
# CONEXÃO COM A BASE DE DADOS SUPABASE
# ---------------------------------------------------------
SUPABASE_URL = "https://ekqemmqbgesyvngbiqyk.supabase.co"
SUPABASE_KEY = "sb_publishable_pLuBSE1xQymIoRqONHDJMA_HUZMw23I"

def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()
BUCKET_STORAGE = "Funcionarios"
ESPECIES_MADEIRA = ["Angelim Vermelho", "Macaranduba", "Ipe", "Cumaru", "Jatobá", "Cupiúba", "Itaúba", "Guarubatinga", "Piquiá", "Loro Vermelho", "Roxinho"]

# ---------------------------------------------------------
# FUNÇÕES DE VALIDAÇÃO E LIMPEZA
# ---------------------------------------------------------
def validar_cpf(cpf):
    cpf = "".join([c for c in str(cpf) if c.isdigit()])
    if len(cpf) != 11 or cpf == cpf[0] * 11: return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    digito1 = (soma * 10) % 11
    if digito1 == 10: digito1 = 0
    if digito1 != int(cpf[9]): return False
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    digito2 = (soma * 10) % 11
    if digito2 == 10: digito2 = 0
    if digito2 != int(cpf[10]): return False
    return True

def limpar_nome_arquivo(texto):
    nfkd = unicodedata.normalize('NFKD', str(texto))
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return "".join([c if c.isalnum() or c in "._-" else "_" for c in sem_acento])

# ---------------------------------------------------------
# FUNÇÕES GERADORAS (PIX & PDFs)
# ---------------------------------------------------------
def formata_pix(chave, valor, nome="Colaborador", cidade="Macapa"):
    nome = ''.join(c for c in unicodedata.normalize('NFD', str(nome)) if unicodedata.category(c) != 'Mn')[:25].strip()
    cidade = ''.join(c for c in unicodedata.normalize('NFD', str(cidade)) if unicodedata.category(c) != 'Mn')[:15].strip()
    try: valor_str = f"{float(valor):.2f}"
    except: valor_str = "0.00"
    chave = str(chave).replace(" ", "")
    payload_format = "000201"
    gui = "0014br.gov.bcb.pix"
    chave_len = f"{len(chave):02d}"
    merc_account_info = f"{gui}01{chave_len}{chave}"
    merc_account_len = f"26{len(merc_account_info):02d}{merc_account_info}"
    merc_category_code = "52040000"
    trans_currency = "5303986"
    trans_amount = f"54{len(valor_str):02d}{valor_str}"
    country_code = "5802BR"
    merc_name = f"59{len(nome):02d}{nome}"
    merc_city = f"60{len(cidade):02d}{cidade}"
    add_data_field = "62070503***"
    payload = f"{payload_format}{merc_account_len}{merc_category_code}{trans_currency}{trans_amount}{country_code}{merc_name}{merc_city}{add_data_field}6304"
    polynomial, crc = 0x1021, 0xFFFF
    for char in payload:
        crc ^= (ord(char) << 8)
        for _ in range(8):
            crc = (crc << 1) ^ polynomial if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return payload + f"{crc:04X}"

def gerar_pdf_ficha_epi(nome, cpf, cargo, setor, data_adm, opcao_alojamento, contato_emergencia, epis_entregues, autoriza_imagem, foto_camera=None, canvas_result=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "FLORESTAL AMAZONIA - TERMO DE ADMISSAO E ENTREGA DE EPI", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 6, "Conforme Norma Regulamentadora NR-31 / MTE e Padroes FSC", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "1. DADOS DO COLABORADOR", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"Nome Completo: {nome}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"CPF: {cpf} | Setor: {setor} | Cargo: {cargo}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Alojamento: {opcao_alojamento.upper()} | Emergencia: {contato_emergencia}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "2. UNIFORME E EPIs", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for item in epis_entregues:
        item_limpo = item.replace('ç', 'c').replace('ã', 'a').replace('í', 'i').replace('ó', 'o').replace('á', 'a').replace('ê', 'e')
        pdf.cell(0, 5, f"[ X ] {item_limpo}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "3. AUTORIZACAO DE USO DE IMAGEM (LGPD)", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    status_auth = "[ X ] SIM, AUTORIZO" if "Sim" in autoriza_imagem else "[ X ] NAO AUTORIZO"
    pdf.cell(0, 5, f"Opcao: {status_auth}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    temp_foto_path, temp_sig_path = None, None
    try:
        if foto_camera is not None:
            foto_pil = Image.open(io.BytesIO(foto_camera.getvalue())).convert("RGB")
            tmp1 = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp1.close() 
            foto_pil.save(tmp1.name, format="JPEG")
            temp_foto_path = tmp1.name

        if canvas_result is not None and canvas_result.image_data is not None:
            if canvas_result.json_data and len(canvas_result.json_data.get("objects", [])) > 0:
                img_array = canvas_result.image_data.astype('uint8')
                sig_rgba = Image.fromarray(img_array, mode='RGBA')
                sig_rgb = Image.new("RGB", sig_rgba.size, (255, 255, 255))
                sig_rgb.paste(sig_rgba, mask=sig_rgba.split()[3])
                tmp2 = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                tmp2.close()
                sig_rgb.save(tmp2.name, format="JPEG")
                temp_sig_path = tmp2.name

        y_start = pdf.get_y() + 2
        if temp_foto_path:
            pdf.image(temp_foto_path, x=15, y=y_start, w=45, h=35)
            pdf.set_xy(15, y_start + 36)
            pdf.cell(45, 5, "Foto", border=False, align="C")
        if temp_sig_path:
            x_sig = 110 if temp_foto_path else 15
            pdf.image(temp_sig_path, x=x_sig, y=y_start, w=60, h=30)
            pdf.set_xy(x_sig, y_start + 31)
            pdf.cell(60, 5, "Assinatura", border=False, align="C")
    except Exception as e: pass
    finally:
        if temp_foto_path and os.path.exists(temp_foto_path): os.remove(temp_foto_path)
        if temp_sig_path and os.path.exists(temp_sig_path): os.remove(temp_sig_path)

    pdf.set_y(pdf.get_y() + 15)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", border=False, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())

def gerar_pdf_cadastro_completo(ficha_epi_bytes, documentos_extras):
    writer = PdfWriter()
    writer.append(io.BytesIO(ficha_epi_bytes))
    for arq in documentos_extras:
        if arq is not None:
            bytes_arq = arq.getvalue()
            if hasattr(arq, 'name') and "pdf" in arq.name.lower():
                try: writer.append(io.BytesIO(bytes_arq))
                except: pass
            else:
                try:
                    img = Image.open(io.BytesIO(bytes_arq)).convert("RGB")
                    tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    tmp_img.close()
                    img.save(tmp_img.name, format="JPEG")
                    pdf_img = FPDF()
                    pdf_img.add_page()
                    pdf_img.image(tmp_img.name, x=10, y=10, w=190)
                    writer.append(io.BytesIO(bytes(pdf_img.output())))
                    os.remove(tmp_img.name)
                except: pass
    output_io = io.BytesIO()
    writer.write(output_io)
    return output_io.getvalue()

def gerar_pdf_resumo_acerto(colab, faltas, adiantamentos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "FLORESTAL AMAZONIA - RESUMO DE ACERTO CONTABIL", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "1. DADOS DO COLABORADOR DESLIGADO", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    nome = str(colab.get('nome_completo', '')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o')
    cargo = str(colab.get('cargo', '')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o')
    motivo = str(colab.get('motivo_desligamento', 'Nao informado')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o').replace('\n', ' ')
    pdf.cell(0, 6, f"Nome Completo: {nome} | CPF: {colab.get('cpf', '')} | Cargo: {cargo}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.multi_cell(0, 5, f"Motivo do Desligamento: {motivo}")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "2. RESUMO DE FALTAS E ADIANTAMENTOS", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    if faltas: pdf.cell(0, 6, f"Total de faltas: {len(faltas)}", border=False, new_x="LMARGIN", new_y="NEXT")
    try: total_adiant = sum(float(a.get('valor', 0) or 0) for a in adiantamentos)
    except: total_adiant = 0.0
    pdf.cell(0, 10, f"TOTAL DE ADIANTAMENTOS A DESCONTAR NO ACERTO: R$ {total_adiant:.2f}", border=False, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())

def gerar_pdf_consolidado_folha(mes, adiantamentos, faltas):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, f"CONSOLIDADO DE ADIANTAMENTOS E FALTAS - {mes}", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "1. ADIANTAMENTOS", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    total_ad = 0
    if not adiantamentos: pdf.cell(0, 6, "Nenhum adiantamento neste periodo.", border=False, new_x="LMARGIN", new_y="NEXT")
    else:
        for a in adiantamentos:
            try: vlr = float(a.get('valor', 0) or 0)
            except: vlr = 0.0
            total_ad += vlr
            pdf.cell(0, 6, f"- {a.get('beneficiario')} | R$ {vlr:.2f} | Obs: {str(a.get('descricao'))[:40]}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.cell(0, 6, f"TOTAL DE ADIANTAMENTOS: R$ {total_ad:.2f}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "2. FALTAS REGISTRADAS", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    if not faltas: pdf.cell(0, 6, "Nenhuma falta registrada.", border=False, new_x="LMARGIN", new_y="NEXT")
    else:
        for f in faltas:
            dt = "/".join(str(f.get('data_falta', '')).split("-")[::-1])
            pdf.cell(0, 6, f"- {f.get('nome_colaborador')} | Data: {dt} | Motivo: {str(f.get('observacao'))[:40]}", border=False, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())

# ---------------------------------------------------------
# DASHBOARDS REUTILIZÁVEIS PROFISSIONAIS
# ---------------------------------------------------------
def render_dashboard_floresta():
    try:
        prod_db = supabase.table("producao_diaria").select("*").execute().data
        vend_db = supabase.table("vendas_tora").select("*").execute().data
    except: prod_db, vend_db = [], []
    
    t_rom = sum(float(p.get('volume_romaneado', 0) or 0) for p in prod_db)
    t_trans = sum(float(p.get('volume_transportado', 0) or 0) for p in prod_db)
    t_vend = sum(float(v.get('volume_vendido', 0) or 0) for v in vend_db)
    
    estoque_umf = t_rom - t_trans
    estoque_patio = t_trans - t_vend
    
    ultimo_arrastado = 0.0
    media_arrastado = 0.0
    if prod_db:
        prod_db_sorted = sorted(prod_db, key=lambda x: x.get('data_producao') or '')
        ultimo_arrastado = float(prod_db_sorted[-1].get('volume_arrastado', 0) or 0)
        dias_arrasto = [float(p.get('volume_arrastado', 0) or 0) for p in prod_db if float(p.get('volume_arrastado', 0) or 0) > 0]
        if dias_arrasto: media_arrastado = sum(dias_arrasto) / len(dias_arrasto)

    st.markdown("### 🌲 Resumo Gerencial - Floresta (UMF e Pátio)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saldo da UMF (m³)", f"{estoque_umf:,.2f}", "Romaneado - Transportado", delta_color="off")
    c2.metric("Saldo do Pátio Baldeio (m³)", f"{estoque_patio:,.2f}", "Transportado - Vendido", delta_color="off")
    c3.metric("Total Romaneado na Safra (m³)", f"{t_rom:,.2f}")
    c4.metric("Último Arrastado Diário (m³)", f"{ultimo_arrastado:,.2f}", f"Média Diária: {media_arrastado:,.2f} m³", delta_color="normal")
    st.divider()

def render_dashboard_serraria():
    try:
        prod = supabase.table("producao_industrial").select("*").eq("tipo_produto", "Madeira Serrada").execute().data
        vend = supabase.table("vendas_serraria").select("*").execute().data
    except: prod, vend = [], []
    
    st.markdown("### 🪚 Dashboard Executivo - Serraria")
    geral_m3 = sum(float(p.get('volume_serrado', 0) or 0) for p in prod) - sum(float(v.get('volume_vendido', 0) or 0) for v in vend)
    st.metric("📦 Saldo Geral em Estoque de Madeira Serrada (m³)", f"{geral_m3:,.2f}")
    
    dados = []
    for esp in ESPECIES_MADEIRA:
        pt = sum(float(p.get('volume_tora', 0) or 0) for p in prod if p.get('especie') == esp)
        ps = sum(float(p.get('volume_serrado', 0) or 0) for p in prod if p.get('especie') == esp)
        vs = sum(float(v.get('volume_vendido', 0) or 0) for v in vend if v.get('especie') == esp)
        est = ps - vs
        fator = (pt / ps) if ps > 0 else 0.0
        
        if pt > 0 or ps > 0 or vs > 0:
            dados.append({
                "Espécie": esp, 
                "Tora Consumida (m³)": f"{pt:.2f}", 
                "Serrado Produzido (m³)": f"{ps:.2f}", 
                "Fator Conv. (Tora/Serrado)": f"{fator:.2f}", 
                "Total Vendido (m³)": f"{vs:.2f}",
                "Estoque Atual (m³)": f"{est:.2f}"
            })
            
    if dados: st.dataframe(pd.DataFrame(dados), use_container_width=True, hide_index=True)
    else: st.info("Sem dados de produção ou vendas cadastrados para a Serraria.")
    st.divider()

def render_dashboard_carvoaria():
    try:
        prod = supabase.table("producao_carvao").select("*").execute().data
        vend = supabase.table("vendas_carvao").select("*").execute().data
    except: prod, vend = [], []
    
    st.markdown("### 🔥 Dashboard Executivo - Carvoaria")
    dados_carvao = []
    for m in ["Saca_Marisa", "Brasa_Brasil"]:
        for t in [3, 6, 25]:
            p_tot = sum(float(x.get('quantidade', 0) or 0) for x in prod if x.get('marca') == m and x.get('tamanho_saca') == t)
            v_tot = sum(float(x.get('quantidade', 0) or 0) for x in vend if x.get('marca') == m and x.get('tamanho_saca') == t)
            est = p_tot - v_tot
            if p_tot > 0 or v_tot > 0:
                dados_carvao.append({
                    "Marca": m.replace('_', ' '), "Tamanho da Saca": f"{t} kg",
                    "Produzidas (Total)": int(p_tot), "Vendidas (Total)": int(v_tot), "Saldo em Estoque": int(est)
                })
                
    if dados_carvao: st.dataframe(pd.DataFrame(dados_carvao), use_container_width=True, hide_index=True)
    else: st.info("Sem dados de produção ou vendas cadastrados para a Carvoaria.")
    st.divider()

# ---------------------------------------------------------
# COMPONENTES COMPARTILHADOS (FALTAS, COLABORADORES, PAGAMENTOS)
# ---------------------------------------------------------
def renderizar_registro_faltas(setor_filtro=None):
    st.subheader("❌ Registro de Faltas Operacionais")
    try:
        query = supabase.table("colaboradores").select("id, nome_completo, setor").eq("status_fluxo", "Operação Liberada")
        aptos = query.execute().data
    except: aptos = []
    
    if aptos and setor_filtro: 
        aptos = [c for c in aptos if c.get('setor') == setor_filtro]
        
    if aptos:
        opcoes = {c['nome_completo']: c['id'] for c in aptos}
        colab_nome = st.selectbox("Selecione o Colaborador:", list(opcoes.keys()), key=f"sel_falta_{setor_filtro}")
        dt_falta = st.date_input("Data da Falta", key=f"dt_falta_{setor_filtro}")
        obs = st.text_area("Motivo / Observação", key=f"obs_falta_{setor_filtro}")
        if st.button("Registrar Falta e Enviar para o RH", key=f"btn_falta_{setor_filtro}"):
            try:
                supabase.table("registro_faltas").insert({
                    "id_colaborador": opcoes[colab_nome], "nome_colaborador": colab_nome,
                    "data_falta": dt_falta.strftime("%Y-%m-%d"), "observacao": obs, "status_falta": "Pendente",
                    "cadastrado_por": email_logado
                }).execute()
                st.success("✅ Falta registrada com sucesso! O RH foi notificado para o fechamento mensal.")
            except Exception as e:
                st.error(f"Erro ao registrar falta. Detalhe: {e}")
    else: st.warning("Nenhum colaborador ativo encontrado para este setor.")

def renderizar_painel_colaboradores_ativos():
    st.markdown("---")
    st.subheader("👥 Colaboradores em Operação (Ativos)")
    try: ativos = supabase.table("colaboradores").select("*").eq("status_fluxo", "Operação Liberada").execute().data
    except: ativos = []
    if not ativos:
        st.info("Nenhum colaborador com status de Operação Liberada no momento.")
        return
    termo_busca = st.text_input("🔍 Buscar Colaborador (Nome ou CPF):", "", key="busca_colab_ativo")
    if termo_busca:
        termo_l = termo_busca.lower()
        ativos = [c for c in ativos if termo_l in str(c.get('nome_completo', '')).lower() or termo_l in str(c.get('cpf', ''))]
    dados_tabela = []
    for idx, c in enumerate(ativos, 1):
        dt_adm_br = "/".join(c.get('data_admissao', '').split("-")[::-1]) if c.get('data_admissao') else 'N/A'
        dados_tabela.append({
            "Nº": idx, "Nome Completo": c.get('nome_completo'), "CPF": c.get('cpf'), "Cargo": c.get('cargo'),
            "Setor": c.get('setor'), "Alojamento": c.get('opcao_alojamento', 'Rede'),
            "Admissão": dt_adm_br, "PIX": c.get('chave_pix', 'Não cad.'), "ASO": "Ver" if c.get('url_aso') else "Não"
        })
    st.dataframe(dados_tabela, use_container_width=True, hide_index=True)

def renderizar_solicitacao_pagamento(perfil):
    st.subheader("💸 Solicitação de Ordens de Pagamento")
    tipo = st.radio("Selecione o Tipo:", ["Diária", "Adiantamento Salarial", "Pagamento Avulso (Fornecedores/Outros)"], horizontal=True)
    col1, col2 = st.columns(2)
    with col1:
        vlr = st.number_input("Valor (R$)", min_value=0.01, value=100.0)
        venc = st.date_input("Data de Vencimento")
        desc = st.text_area("Descrição do Fato Gerador (Porquê do pagamento)")
    with col2:
        if tipo in ["Diária", "Adiantamento Salarial"]:
            try: aptos = supabase.table("colaboradores").select("id, nome_completo, chave_pix").eq("status_fluxo", "Operação Liberada").execute().data
            except: aptos = []
            if aptos:
                opcoes = {c['nome_completo']: c for c in aptos}
                sel = opcoes[st.selectbox("Selecionar Colaborador:", list(opcoes.keys()))]
                beneficiario = sel['nome_completo']
                id_colab = sel['id']
                pix = st.text_input("Chave PIX", value=sel.get('chave_pix', ''))
            else:
                st.warning("Nenhum colaborador ativo encontrado.")
                return
        else:
            beneficiario = st.text_input("Nome do Beneficiário")
            id_colab = None
            pix = st.text_input("Chave PIX")
    if st.button("Gerar Ordem de Pagamento"):
        if not beneficiario or not pix: st.error("Preencha o beneficiário e o PIX.")
        else:
            try:
                supabase.table("lancamentos_financeiros").insert({
                    "descricao": desc, "categoria": tipo, "valor": float(vlr), "data_vencimento": venc.strftime("%Y-%m-%d"), 
                    "status_lancamento": "Aprovação Pendente Financeiro", "beneficiario": beneficiario, "pix": pix,
                    "id_colaborador": id_colab, "criado_por": email_logado
                }).execute()
                st.success("✅ Ordem gerada e enviada para Aprovação do Financeiro (Módulo Aprovações)!")
            except Exception as e:
                st.error(f"Erro ao conectar com o banco. Atualize a página. {e}")

def renderizar_reprovados(email):
    try: reprovados = supabase.table("lancamentos_financeiros").select("*").eq("criado_por", email).eq("status_lancamento", "Reprovado").execute().data
    except: reprovados = []
    if reprovados:
        st.error("🚨 Você tem ordens de pagamento que foram REPROVADAS pelo Financeiro.")
        for r in reprovados:
            v_atual = float(r.get('valor', 0) or 0)
            with st.expander(f"{r.get('categoria', '')} - {r.get('beneficiario', '')} (R$ {v_atual:.2f})"):
                st.write(f"**Motivo da Recusa:** {r.get('motivo_recusa')}")
                novo_vlr = st.number_input("Corrigir Valor", value=v_atual, key=f"vlr_{r['id']}")
                nova_desc = st.text_area("Corrigir Descrição", value=r.get('descricao', ''), key=f"desc_{r['id']}")
                novo_pix = st.text_input("Corrigir PIX", value=r.get('pix',''), key=f"pix_{r['id']}")
                colA, colB = st.columns(2)
                if colA.button("Reenviar para Aprovação", key=f"reenv_{r['id']}"):
                    supabase.table("lancamentos_financeiros").update({
                        "valor": float(novo_vlr), "descricao": nova_desc, "pix": novo_pix,
                        "status_lancamento": "Aprovação Pendente Financeiro", "motivo_recusa": None
                    }).eq("id", r['id']).execute(); st.rerun()
                if colB.button("Cancelar Ordem Definitivamente", key=f"canc_{r['id']}"):
                    supabase.table("lancamentos_financeiros").update({"status_lancamento": "Cancelado"}).eq("id", r['id']).execute(); st.rerun()

# ---------------------------------------------------------
# SISTEMA DE LOGIN SIMPLIFICADO (SEM BLOQUEIOS SUPABASE)
# ---------------------------------------------------------
def gerenciar_autenticacao():
    st.sidebar.title("🔐 Acesso ao Sistema")
    
    if "usuario_autenticado" not in st.session_state:
        st.session_state.usuario_autenticado = False
        st.session_state.perfil_usuario = None
        st.session_state.email_usuario = None
        
    if st.session_state.usuario_autenticado:
        st.sidebar.success(f"Logado como:\n**{st.session_state.perfil_usuario}**")
        if st.sidebar.button("🚪 Sair"):
            st.session_state.usuario_autenticado = False
            st.session_state.perfil_usuario = None
            st.session_state.email_usuario = None
            st.rerun()
        return True

    with st.sidebar.form("form_login"):
        perfis = [
            "Selecione o seu setor...",
            "RH Cadastral - Unificado",
            "Engenharia Florestal (Jean Gustavo)",
            "Operacional Indústria - Serraria (Felipe)",
            "Operacional Indústria - Carvoaria (Nelson)",
            "Lançamentos Financeiros (Jonas)",
            "Execução de Pagamentos (Matheus)",
            "Proprietário / Diretoria (Gean)"
        ]
        
        perfil_selecionado = st.selectbox("Quem está a aceder?", perfis)
        st.caption("Apenas a Diretoria necessita de palavra-passe.")
        senha_login = st.text_input("Palavra-passe", type="password")
        
        submit_login = st.form_submit_button("Entrar")
        
        if submit_login:
            if perfil_selecionado == "Selecione o seu setor...":
                st.error("Por favor, selecione um setor na lista.")
            elif perfil_selecionado == "Proprietário / Diretoria (Gean)" and senha_login != "admin":
                # A senha padrão da diretoria é "admin" (Pode alterar aqui se quiser)
                st.error("Palavra-passe incorreta para a Diretoria.")
            else:
                st.session_state.perfil_usuario = perfil_selecionado
                # Criamos um email fictício para a base de dados aceitar o registo do utilizador
                if perfil_selecionado == "Proprietário / Diretoria (Gean)":
                    st.session_state.email_usuario = "gean@florestalamazonia.com"
                else:
                    st.session_state.email_usuario = "operacao_livre@florestalamazonia.com"
                
                st.session_state.usuario_autenticado = True
                st.rerun()
                
    with st.sidebar.expander("📱 Como instalar o App"):
        st.markdown("""
        **No Celular (Android):**  
        Abra no Chrome, clique nos **3 pontinhos** (topo direito) e escolha **Adicionar à tela inicial**.
        
        **No iPhone (iOS):**  
        Abra no Safari, clique no ícone de **Compartilhar** (quadrado com seta para cima) e escolha **Adicionar à Tela de Início**.
        """)
        
    return False

if not gerenciar_autenticacao(): st.stop()

perfil_banco = st.session_state.perfil_usuario
email_logado = st.session_state.email_usuario

if perfil_banco == "Proprietário / Diretoria (Gean)":
    st.sidebar.warning("👑 **MODO ADMINISTRADOR**")
    perfil_usuario = st.sidebar.selectbox("Navegar como:", ["Proprietário / Diretoria (Gean)", "RH Cadastral - Unificado", "Engenharia Florestal (Jean Gustavo)", "Operacional Indústria - Serraria (Felipe)", "Operacional Indústria - Carvoaria (Nelson)", "Lançamentos Financeiros (Jonas)", "Execução de Pagamentos (Matheus)"])
else:
    perfil_usuario = perfil_banco
    st.sidebar.info(f"Painel Operacional")

# ---------------------------------------------------------
# MÓDULOS ESPECÍFICOS DE CADA SETOR
# ---------------------------------------------------------

if perfil_usuario == "RH Cadastral - Unificado":
    st.header("📋 Recursos Humanos")
    
    # --- ALERTA GIGANTE DE RETORNO DE TREINAMENTO (APTO OU INAPTO) ---
    try: retornos = supabase.table("colaboradores").select("*").in_("status_fluxo", ["Aguardando Contrato", "Inapto"]).execute().data
    except: retornos = []
    if retornos:
        st.error("🚨 ATENÇÃO: RETORNO DE AVALIAÇÃO DE TREINAMENTO")
        for r in retornos:
            with st.expander(f"📌 {r['nome_completo']} | Status: {r['status_fluxo'].upper()}", expanded=True):
                if r['status_fluxo'] == "Inapto":
                    st.warning("⚠️ Este colaborador obteve nota abaixo de 70 no treinamento e foi reprovado pela operação.")
                    if st.button("Dispensar (Desligamento)", key=f"disp_{r['id']}"):
                        supabase.table("colaboradores").update({"status_fluxo": "Desligamento da empresa"}).eq("id", r['id']).execute()
                        st.success("Colaborador encaminhado para Desligamento.")
                        st.rerun()
                else:
                    st.success("✅ Apto! Envie para Contabilidade. Faça o upload do Contrato Assinado para liberar a Operação.")
                    contrato_up = st.file_uploader("Anexar Contrato de Trabalho Assinado (PDF/Imagem)", key=f"ct_up_{r['id']}")
                    if contrato_up:
                        if st.button("🌟 Ativar para Operação", key=f"ativar_{r['id']}", type="primary"):
                            nm_limpo = limpar_nome_arquivo(r['nome_completo'])
                            cpf_limpo = "".join([c for c in str(r.get('cpf','')) if c.isdigit()])
                            ext = "pdf" if "pdf" in contrato_up.name.lower() else "jpg"
                            caminho = f"{nm_limpo}_{cpf_limpo}/Contrato/Contrato_Final_Assinado.{ext}"
                            try: supabase.storage.from_(BUCKET_STORAGE).upload(caminho, contrato_up.getvalue(), {"upsert": "true"})
                            except: pass
                            url_ct = supabase.storage.from_(BUCKET_STORAGE).get_public_url(caminho)
                            supabase.table("colaboradores").update({"status_fluxo": "Operação Liberada", "url_contrato_trabalho": url_ct}).eq("id", r['id']).execute()
                            st.success("Colaborador ATIVO na Operação com sucesso!")
                            st.rerun()
        st.markdown("---")
    
    aba_cadastro, aba_desligamentos, aba_folha_rh, aba_ativos_rh, aba_folha_formacao = st.tabs(["🆕 Cadastro Inicial", "🚪 Desligamentos", "💵 Holerites", "👥 Colaboradores", "📂 Folha em Formação (Consolidado)"])
    
    with aba_cadastro:
        if "cadastro_concluido" in st.session_state:
            st.success("✅ Colaborador cadastrado com sucesso! O processo foi enviado automaticamente para a fila de Treinamento do Setor Operacional correspondente.")
            st.download_button("📥 Baixar Ficha de Admissão e EPI Completa (PDF)", st.session_state.cadastro_concluido['pdf'], file_name=f"Cadastro_{st.session_state.cadastro_concluido['nome']}.pdf", mime="application/pdf")
            st.info("Imprima este documento e guarde a via física assinada para auditoria FSC.")
            if st.button("🔙 Limpar e Fazer Novo Cadastro"):
                del st.session_state.cadastro_concluido
                st.rerun()
        else:
            EPI_POR_SETOR = {
                "Indústria / Carvoaria": {
                    "Soldador": ["PROTETOR AURICULAR TIPO PLUG", "AVENTAL DE RASPA", "MANGOTE", "MÁSCARA DE SOLDA", "RESPIRADOR", "LUVA RASPA", "BOTAS COM BIQUEIRA", "LUVA NITRILICA"],
                    "Serviços Gerais": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Serrador": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Romaneador Nível I (Serraria)": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Prancheiro": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Multileiro": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Gerente de Produção": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Empilhador": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Destopador": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Circuleiro de Aproveitamento": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Circuleiro": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Bitoleiro": ["CAPACETE COM JUGULAR", "MÁSCARA PFF 2", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Almoxarife": ["CAPACETE COM JUGULAR", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Ajudante Geral Nível 1 (Serraria)": ["CAPACETE COM JUGULAR", "MÁSCARA PFF 2", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Ajudante de Multileiro": ["CAPACETE COM JUGULAR", "MÁSCARA PFF 2", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Ajudante de Destopador": ["CAPACETE COM JUGULAR", "MÁSCARA PFF 2", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Amarrador de Ripas": ["CAPACETE COM JUGULAR", "MÁSCARA PFF 2", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "LUVA PIGMENTADA"],
                    "Laminador": ["PROTETOR AURICULAR PLUG", "LUVA NITRICA", "ÓCULOS DE SEGURANÇA", "MÁSCARA PFF 2", "LUVA PIGMENTADA", "AVENTAL RASPA"],
                    "Ajudante Geral Nível 5 (Carvoaria)": ["PROTETOR AURICULAR PLUG", "RESPIRADOR", "LUVAS EMBORRACHADAS", "CAPACETE COM JUGULAR", "BOTAS COM BIQUEIRA", "CALÇA DE MOTOSSERRISTA"],
                    "Ajudante Geral Nível 4 (Carvoaria)": ["PROTETOR AURICULAR PLUG", "RESPIRADOR", "LUVAS EMBORRACHADAS", "CAPACETE COM JUGULAR", "BOTAS COM BIQUEIRA", "CALÇA DE MOTOSSERRISTA"],
                    "Carbonizador": ["PROTETOR AURICULAR PLUG", "RESPIRADOR", "LUVAS EMBORRACHADAS", "CAPACETE COM JUGULAR", "BOTAS COM BIQUEIRA", "CALÇA DE MOTOSSERRISTA"]
                },
                "Floresta": {
                    "Operador de Motosserra": ["CAPACETE MOTOSSERRISTA", "MÁSCARA PFF 2", "LUVA DE MOTOSSERRISTA", "CALÇA DE MOTOSSERRISTA", "BOTAS COM BIQUEIRA", "CAMISETA MANGA LONGA", "PERNEIRAS"],
                    "Romaneador Nível II": ["PROTETOR AURICULAR", "MÁSCARA PFF 2", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "PERNEIRAS", "LUVA RASPA", "LUVA PIGMENTADA", "CAMISETA MANGA LONGA", "CAPACETE COM JUGULAR"],
                    "Planejador": ["PROTETOR AURICULAR", "MÁSCARA PFF 2", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "PERNEIRAS", "LUVA RASPA", "LUVA PIGMENTADA", "CAMISETA MANGA LONGA", "CAPACETE COM JUGULAR"],
                    "Gerente de Produção e Operações": ["PROTETOR AURICULAR", "MÁSCARA PFF 2", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "PERNEIRAS", "LUVA RASPA", "LUVA PIGMENTADA", "CAMISETA MANGA LONGA", "CAPACETE COM JUGULAR"],
                    "Almoxarife": ["PROTETOR AURICULAR", "MÁSCARA PFF 2", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "PERNEIRAS", "LUVA RASPA", "LUVA PIGMENTADA", "CAMISETA MANGA LONGA", "CAPACETE COM JUGULAR"],
                    "Ajudante Geral Nível 3 (Alojamento)": ["AVENTAL PVC", "ÓCULOS DE SEGURANÇA", "LUVA PVC", "BOTAS COM BIQUEIRA", "LUVA NITRICA"],
                    "Ajudante Geral Nível 2 (Extração)": ["PROTETOR AURICULAR", "MÁSCARA PFF 2", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "PERNEIRAS", "LUVA RASPA", "LUVA PIGMENTADA", "CAMISETA MANGA LONGA", "CAPACETE COM JUGULAR"],
                    "Cozinheira": ["AVENTAL IMPERMEÁVEL", "LUVAS NITRILICA", "ÓCULOS DE SEGURANÇA", "BOTAS COM BIQUEIRA", "TOUCA DESCARTÁVEL", "LUVAS ANTI-CORTE"],
                    "Operador de Máquinas Pesadas": ["PROTETOR AURICULAR CONCHA", "LUVAS NITRILICA", "ÓCULOS DE SEGURANÇA", "MÁSCARA PFF 2", "VESTIMENTA MANGAS LONGAS", "BOTAS COM BIQUEIRA", "PERNEIRAS"],
                    "Motorista de Caminhão": ["PROTETOR AURICULAR", "LUVAS NITRILICA", "ÓCULOS DE SEGURANÇA", "MÁSCARA PFF 2", "VESTIMENTA MANGAS LONGAS", "BOTAS COM BIQUEIRA", "PERNEIRAS"]
                }
            }
            c_nome, c_cargo = st.columns(2)
            with c_nome:
                nome = st.text_input("Nome Completo")
                cpf = st.text_input("CPF (Somente números ou pontuado)")
                chave_pix_cad = st.text_input("Chave PIX")
                data_adm = st.date_input("Data de Admissão")
            with c_cargo:
                setor_escolhido = st.selectbox("Setor", list(EPI_POR_SETOR.keys()))
                cargo_escolhido = st.selectbox("Cargo", list(EPI_POR_SETOR[setor_escolhido].keys()))
                contato_emergencia = st.text_input("📞 Contato Emergência")
                st.write("⛺ **Alojamento Rural:**")
                opcao_alojamento = st.radio("Escolha:", ["Rede", "Cama", "Não Alojado"], horizontal=True)
            
            def anexar_doc(label, chave):
                st.markdown(f"**{label}**")
                arq = st.file_uploader(f"Anexar {label}", type=["pdf", "jpg", "jpeg", "png"], key=f"arq_{chave}", label_visibility="collapsed")
                cam = None
                if st.checkbox("📸 Ligar Câmera", key=f"chk_{chave}"): cam = st.camera_input("Tire a foto", key=f"cam_{chave}")
                st.markdown("---")
                return cam if cam is not None else arq

            st.subheader("🏥 Documentos Essenciais")
            aso_doc = anexar_doc("1. ASO", "aso")
            doc_pessoal = anexar_doc("2. Documento Pessoal", "doc_pess")
            vacina_doc = anexar_doc("3. Vacinação", "vac")
            residencia_doc = anexar_doc("4. Residência", "res")
            if st.checkbox("Possui filhos < 14 anos?"): certidao_doc = anexar_doc("5. Certidão Nascimento Filho(s)", "cert")
            else: certidao_doc = None
            
            st.subheader("👕 EPIs e Uniforme")
            epis_exigidos = EPI_POR_SETOR[setor_escolhido][cargo_escolhido].copy()
            c_uni_check, c_uni_tam = st.columns([2, 2])
            recebe_uniforme = c_uni_check.checkbox("Recebeu Uniforme", value=True)
            tamanho_uniforme = c_uni_tam.selectbox("Tamanho Uniforme", ["P", "M", "G", "GG", "XG"])
            epis_marcados = []
            if recebe_uniforme: epis_marcados.append(f"UNIFORME COMPLETO (Tam: {tamanho_uniforme})")
                
            cepi1, cepi2 = st.columns(2)
            for i, epi in enumerate(epis_exigidos):
                cd = cepi1 if i % 2 == 0 else cepi2
                chk, cx = cd.columns([6, 4])
                checado = chk.checkbox(epi, key=f"epi_{i}")
                if "BOTA" in epi.upper():
                    ca, num = cx.columns(2)
                    ca_val = ca.text_input("CA", key=f"ca_{i}", label_visibility="collapsed")
                    num_bota = num.text_input("Nº", value="41", key=f"num_{i}", label_visibility="collapsed")
                    if checado: epis_marcados.append(f"{epi} (CA: {ca_val} | Num: {num_bota})")
                else:
                    ca_val = cx.text_input("CA", key=f"ca_{i}", label_visibility="collapsed")
                    if checado: epis_marcados.append(f"{epi} (CA: {ca_val})")
            
            conduta = st.checkbox("Aceito Código Conduta")
            autoriza_imagem = st.radio("Autoriza imagem?", ["Sim", "Não"], horizontal=True)

            st.write("📷 **Foto Rosto**")
            foto_capturada = None
            if "foto_temp" not in st.session_state: st.session_state.foto_temp = None
            if st.checkbox("📸 Câmera Foto"):
                fi = st.camera_input("Tirar Foto", key="cam_rosto")
                if fi is not None: st.session_state.foto_temp = fi
            if st.session_state.foto_temp is not None:
                st.image(st.session_state.foto_temp, width=200)
                foto_capturada = st.session_state.foto_temp

            st.subheader("✍ Assinatura Digital")
            canvas_result = st_canvas(stroke_width=2, background_color="#F0F2F6", height=150, drawing_mode="freedraw", key="canvas")

            if st.button("Concluir Cadastro e Enviar para Treinamento"):
                cpf_limpo = "".join([c for c in str(cpf) if c.isdigit()])
                if not nome.strip() or not cpf.strip(): st.error("Preencha Nome e CPF.")
                elif not validar_cpf(cpf_limpo): st.error("CPF inválido!")
                else:
                    setor_db = "Colheita" if setor_escolhido == "Floresta" else ("Indústria" if setor_escolhido == "Indústria / Carvoaria" else setor_escolhido)
                    docs = [aso_doc, doc_pessoal, vacina_doc, residencia_doc, certidao_doc]
                    pdf_epi = gerar_pdf_ficha_epi(nome, cpf, cargo_escolhido, setor_escolhido, data_adm.strftime("%d/%m/%Y"), opcao_alojamento, contato_emergencia, epis_marcados, autoriza_imagem, foto_capturada, canvas_result)
                    pdf_completo = gerar_pdf_cadastro_completo(pdf_epi, docs)
                    nm = limpar_nome_arquivo(nome)
                    pasta = f"{nm}_{cpf_limpo}"
                    
                    def salvar_arquivo(arq, sub, nm_padrao):
                        if arq is not None:
                            try:
                                ext = "pdf" if (hasattr(arq, 'name') and "pdf" in arq.name.lower()) else "jpg"
                                cam = f"{pasta}/{sub}/{nm_padrao}.{ext}"
                                supabase.storage.from_(BUCKET_STORAGE).upload(cam, arq.getvalue(), {"upsert": "true"})
                                return supabase.storage.from_(BUCKET_STORAGE).get_public_url(cam)
                            except: pass
                        return ""
                    
                    try: supabase.storage.from_(BUCKET_STORAGE).upload(f"{pasta}/Ficha_Epi/Termo.pdf", pdf_epi, {"upsert": "true"})
                    except: pass
                    url_pdf = supabase.storage.from_(BUCKET_STORAGE).get_public_url(f"{pasta}/Ficha_Epi/Termo.pdf")
                    
                    try:
                        supabase.table("colaboradores").insert({
                            "nome_completo": nome.strip(), "cpf": cpf.strip(), "cargo": cargo_escolhido, "setor": setor_db, 
                            "data_admissao": data_adm.strftime("%Y-%m-%d"), "ficha_epi_assinada": True, "codigo_conduta_lido": conduta,
                            "status_fluxo": "Aguardando Treinamento", "url_ficha_pdf": url_pdf, "chave_pix": chave_pix_cad.strip(), 
                            "url_aso": salvar_arquivo(aso_doc, "Aso", "Exame"), "url_documento_pessoal": salvar_arquivo(doc_pessoal, "Docs", "DocPessoal"), 
                            "url_vacina": salvar_arquivo(vacina_doc, "Vacina", "Carteira"), "url_residencia": salvar_arquivo(residencia_doc, "Res", "Comprovante"), 
                            "opcao_alojamento": opcao_alojamento, "contato_emergencia": contato_emergencia.strip(),
                            "autoriza_imagem": autoriza_imagem, "cadastrado_por": email_logado
                        }).execute()
                        st.session_state.cadastro_concluido = {'pdf': pdf_completo, 'nome': nm}
                        st.session_state.foto_temp = None
                        st.rerun()
                    except Exception as err: st.error(f"Erro: {err}")

    with aba_desligamentos:
        st.subheader("Processos de Desligamento")
        try: desligados = supabase.table("colaboradores").select("*").in_("status_fluxo", ["Não Habilitado", "Desligamento da empresa"]).execute().data
        except: desligados = []
        if not desligados: st.info("Nenhum processo pendente.")
        for colab in desligados:
            with st.expander(f"⚠️ {colab.get('nome_completo','')} - Status: {colab.get('status_fluxo','')}"):
                try: faltas_colab = supabase.table("registro_faltas").select("*").eq("id_colaborador", colab['id']).execute().data
                except: faltas_colab = []
                try: adiantamentos_todos = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Adiantamento Salarial").execute().data
                except: adiantamentos_todos = []
                adiantamentos_colab = [a for a in adiantamentos_todos if str(colab.get('nome_completo','')).lower() in str(a.get('beneficiario','')).lower()]
                pdf_acerto = gerar_pdf_resumo_acerto(colab, faltas_colab, adiantamentos_colab)
                st.download_button("📄 Baixar Resumo para Acerto", pdf_acerto, f"Acerto_{colab.get('nome_completo','')}.pdf", "application/pdf", key=f"dl_{colab['id']}")
                if st.button("✅ Confirmar Arquivamento", key=f"arq_rh_{colab['id']}"):
                    supabase.table("colaboradores").update({"status_fluxo": "Acerto Concluído"}).eq("id", colab['id']).execute(); st.rerun()

    with aba_folha_rh:
        st.subheader("Envio de Holerites")
        try: ativos_rh = supabase.table("colaboradores").select("id, nome_completo, cpf, cargo, setor, chave_pix").eq("status_fluxo", "Operação Liberada").execute().data
        except: ativos_rh = []
        if not ativos_rh: st.warning("Nenhum colaborador ativo.")
        else:
            opcoes_folha = {f"{c['nome_completo']} ({c['cargo']})": c for c in ativos_rh}
            colab_sel_str = st.selectbox("Colaborador:", list(opcoes_folha.keys()))
            colab_folha = opcoes_folha[colab_sel_str]
            mes_ref = st.text_input("Mês Referência", value=datetime.now().strftime("%B/%Y").capitalize())
            valor_liq = st.number_input("Valor Líquido (R$)", min_value=1.0, value=1500.0)
            holerite_pdf = st.file_uploader("Anexar Holerite (PDF)", type=["pdf"])
            if st.button("Gerar Ordem Pagamento Folha"):
                if not holerite_pdf: st.error("Anexo obrigatório!")
                else:
                    try:
                        supabase.table("lancamentos_financeiros").insert({
                            "descricao": f"Folha de Pagamento | Ref: {mes_ref}", "categoria": "Folha de Pagamento", "valor": float(valor_liq),
                            "beneficiario": colab_folha['nome_completo'], "pix": colab_folha.get('chave_pix', ''),
                            "id_colaborador": colab_folha['id'], "data_vencimento": datetime.now().strftime("%Y-%m-%d"), 
                            "status_lancamento": "Aprovação Pendente Financeiro"
                        }).execute()
                        st.success("✅ Enviado!")
                    except Exception as e: st.error(f"Erro no banco: {e}")

    with aba_ativos_rh: renderizar_painel_colaboradores_ativos()

    with aba_folha_formacao:
        st.subheader("Gestão Mensal: Adiantamentos e Faltas")
        mes_atual = st.selectbox("Mês Referência Consolidado", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"])
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📄 Gerar Consolidado em PDF"):
                try: adiantamentos = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Adiantamento Salarial").execute().data
                except: adiantamentos = []
                try: faltas = supabase.table("registro_faltas").select("*").execute().data
                except: faltas = []
                pdf = gerar_pdf_consolidado_folha(mes_atual, adiantamentos, faltas)
                st.download_button("📥 Baixar PDF Contabilidade", pdf, f"Consolidado_{mes_atual}.pdf", "application/pdf")
        
        with c2:
            st.write("📊 **Importação de Folha em Massa (Excel/CSV)**")
            arq_folha = st.file_uploader("Subir Planilha de Pagamentos", type=["xlsx", "csv"])
            
            if st.button("Processar Planilha e Gerar Pagamentos") and arq_folha:
                try:
                    if arq_folha.name.endswith('.csv'):
                        df_folha = pd.read_csv(arq_folha)
                    else:
                        df_folha = pd.read_excel(arq_folha)
                    
                    df_folha.columns = df_folha.columns.str.strip()
                    cols = {str(col).lower(): col for col in df_folha.columns}
                    
                    col_nome = cols.get('nome', 'Nome')
                    col_pix = cols.get('chave pix', cols.get('pix', 'Chave PIX'))
                    col_valor = cols.get('valor liquido', cols.get('valor', 'Valor Liquido'))

                    ordens_geradas = 0
                    for index, row in df_folha.iterrows():
                        if pd.isna(row.get(col_nome)): continue
                        
                        val_str = str(row.get(col_valor, 0)).replace('R$', '').replace('.', '').replace(',', '.').strip()
                        try: val_float = float(val_str)
                        except: val_float = 0.0

                        if val_float > 0:
                            supabase.table("lancamentos_financeiros").insert({
                                "descricao": f"Folha de Pagamento em Massa - {mes_atual}",
                                "categoria": "Folha de Pagamento",
                                "valor": val_float,
                                "beneficiario": str(row[col_nome]),
                                "pix": str(row.get(col_pix, '')),
                                "data_vencimento": datetime.now().strftime("%Y-%m-%d"),
                                "status_lancamento": "Lançado - Aguardando Pagamento", 
                                "criado_por": email_logado
                            }).execute()
                            ordens_geradas += 1
                            
                    st.success(f"✅ Sucesso! {ordens_geradas} ordens foram geradas e enviadas ao módulo de Execução.")
                except Exception as e:
                    st.error(f"Erro ao processar a planilha. Certifique-se de que o arquivo não está corrompido. Detalhe técnico: {e}")


elif perfil_usuario == "Engenharia Florestal (Jean Gustavo)":
    st.header("🌲 Engenharia Florestal (Campo e UMF)")
    
    try: treinandos = supabase.table("colaboradores").select("*").eq("status_fluxo", "Aguardando Treinamento").eq("setor", "Colheita").execute().data
    except: treinandos = []
    if treinandos:
        st.error("⚠️ ALERTA DE NOVO COLABORADOR: TREINAMENTO PENDENTE")
        for t in treinandos:
            with st.expander(f"📚 Avaliar: {t['nome_completo']} ({t['cargo']})", expanded=True):
                st.write("Um novo colaborador foi registado pelo RH. Realize o treinamento de campo e suba a nota.")
                nota = st.number_input("Nota do Treinamento (0 a 100)", 0, 100, 0, key=f"n_{t['id']}")
                cert = st.file_uploader("Upload do Certificado de Treinamento", key=f"cert_{t['id']}")
                if st.button("Finalizar Avaliação e Enviar para RH", key=f"btn_t_{t['id']}"):
                    if not cert: st.error("O upload do certificado é obrigatório!")
                    else:
                        status = "Aguardando Contrato" if nota >= 70 else "Inapto"
                        supabase.table("colaboradores").update({"status_fluxo": status}).eq("id", t['id']).execute()
                        st.success("Avaliação enviada ao RH!")
                        st.rerun()
        st.markdown("---")
        
    menu = st.radio("Ações:", ["📊 Produção e Romaneio", "💸 Diárias/Pagamentos Avulsos", "❌ Registro de Faltas"], horizontal=True)
    st.divider()

    if menu == "📊 Produção e Romaneio":
        aba_in, aba_dash, aba_upload = st.tabs(["📝 Lançamentos Diários", "📈 Dashboard e Estoques", "📤 Upload em Lote"])
        with aba_in:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("🌲 Lançamento Produção")
                with st.form("form_prod_flor"):
                    dt = st.date_input("Data")
                    vol_arr = st.number_input("Tora Arrastada (m³)", min_value=0.0)
                    vol_rom = st.number_input("Tora Romaneada (m³)", min_value=0.0)
                    vol_trans = st.number_input("Tora Transportada p/ Fora UMF (m³)", min_value=0.0)
                    if st.form_submit_button("Salvar Produção"):
                        supabase.table("producao_diaria").insert({"data_producao": dt.strftime("%Y-%m-%d"),"volume_arrastado": float(vol_arr), "volume_romaneado": float(vol_rom), "volume_transportado": float(vol_trans)}).execute()
                        st.success("Salvo!")
            with c2:
                st.subheader("🤝 Lançamento Vendas (Pátio)")
                with st.form("form_venda_tora"):
                    dt_v = st.date_input("Data")
                    vol_vendido = st.number_input("Toras Vendidas (m³)", min_value=0.0)
                    if st.form_submit_button("Lançar Venda"):
                        supabase.table("vendas_tora").insert({"data_venda": dt_v.strftime("%Y-%m-%d"), "volume_vendido": float(vol_vendido), "cadastrado_por": email_logado}).execute()
                        st.success("Registado!")
        with aba_dash: render_dashboard_floresta()
        with aba_upload:
            st.info("Colunas: Data, Arrastado, Romaneado, Transportado.")
            arq = st.file_uploader("Ficheiro", type=["csv", "xlsx"])
            if st.button("Processar") and arq:
                try:
                    df = pd.read_csv(arq) if arq.name.endswith('.csv') else pd.read_excel(arq)
                    for _, row in df.iterrows():
                        supabase.table("producao_diaria").insert({"data_producao": str(row['Data']), "volume_arrastado": float(row['Arrastado']), "volume_romaneado": float(row['Romaneado']), "volume_transportado": float(row['Transportado'])}).execute()
                    st.success("Concluído!")
                except Exception as e: st.error(f"Erro: {e}")

    elif menu == "💸 Diárias/Pagamentos Avulsos":
        renderizar_reprovados(email_logado)
        renderizar_solicitacao_pagamento(perfil_usuario)
        
    elif menu == "❌ Registro de Faltas":
        renderizar_registro_faltas("Colheita")


elif perfil_usuario == "Operacional Indústria - Carvoaria (Nelson)":
    st.header("🔥 Indústria: Carvoaria")
    menu = st.radio("Ações:", ["🏭 Produção e Vendas (Carvão)", "💸 Ordens de Pagamento", "❌ Registro de Faltas"], horizontal=True)
    st.divider()
    
    if menu == "🏭 Produção e Vendas (Carvão)":
        aba_in, aba_dash = st.tabs(["📝 Lançamentos Diários", "📈 Dashboard Profissional"])
        with aba_in:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("🏭 Lançar Produção")
                with st.form("form_prod_carv"):
                    dt_p = st.date_input("Data Produção")
                    tam = st.selectbox("Saca", [3, 6, 25])
                    marca = st.selectbox("Marca", ["Saca_Marisa", "Brasa_Brasil"])
                    qtd = st.number_input("Quantidade Produzida", min_value=1)
                    if st.form_submit_button("Salvar Produção"):
                        supabase.table("producao_carvao").insert({"data_producao": dt_p.strftime("%Y-%m-%d"), "tamanho_saca": tam, "marca": marca, "quantidade": float(qtd), "cadastrado_por": email_logado}).execute()
                        st.success("Salvo!")
            with c2:
                st.subheader("🤝 Lançar Venda")
                with st.form("form_vend_carv"):
                    dt_v = st.date_input("Data Venda")
                    tam_v = st.selectbox("Saca Vendida", [3, 6, 25])
                    marca_v = st.selectbox("Marca Vendida", ["Saca_Marisa", "Brasa_Brasil"])
                    qtd_v = st.number_input("Quantidade Vendida", min_value=1)
                    if st.form_submit_button("Lançar Venda"):
                        supabase.table("vendas_carvao").insert({"data_venda": dt_v.strftime("%Y-%m-%d"), "tamanho_saca": tam_v, "marca": marca_v, "quantidade": float(qtd_v), "cadastrado_por": email_logado}).execute()
                        st.success("Registado!")
        with aba_dash: render_dashboard_carvoaria()

    elif menu == "💸 Ordens de Pagamento":
        renderizar_reprovados(email_logado)
        renderizar_solicitacao_pagamento(perfil_usuario)
        
    elif menu == "❌ Registro de Faltas":
        renderizar_registro_faltas("Indústria")


elif perfil_usuario == "Operacional Indústria - Serraria (Felipe)":
    st.header("🪚 Indústria: Serraria")
    
    try: treinandos = supabase.table("colaboradores").select("*").eq("status_fluxo", "Aguardando Treinamento").eq("setor", "Indústria").execute().data
    except: treinandos = []
    if treinandos:
        st.error("⚠️ ALERTA DE NOVO COLABORADOR: TREINAMENTO PENDENTE")
        for t in treinandos:
            with st.expander(f"📚 Avaliar: {t['nome_completo']} ({t['cargo']})", expanded=True):
                st.write("Um novo colaborador da Indústria foi registado pelo RH. Realize o treinamento e suba a nota.")
                nota = st.number_input("Nota do Treinamento (0 a 100)", 0, 100, 0, key=f"n_{t['id']}")
                cert = st.file_uploader("Upload do Certificado de Treinamento", key=f"cert_{t['id']}")
                if st.button("Finalizar Avaliação e Enviar para RH", key=f"btn_t_{t['id']}"):
                    if not cert: st.error("O upload do certificado é obrigatório!")
                    else:
                        status = "Aguardando Contrato" if nota >= 70 else "Inapto"
                        supabase.table("colaboradores").update({"status_fluxo": status}).eq("id", t['id']).execute()
                        st.success("Avaliação enviada ao RH!")
                        st.rerun()
        st.markdown("---")

    menu = st.radio("Ações:", ["🪚 Produção e Vendas (Madeira)", "💸 Ordens de Pagamento", "❌ Registro de Faltas"], horizontal=True)
    st.divider()
    
    if menu == "🪚 Produção e Vendas (Madeira)":
        aba_in, aba_dash = st.tabs(["📝 Lançamentos Diários", "📈 Dashboard Profissional"])
        with aba_in:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("🏭 Tora em Madeira Serrada")
                with st.form("form_prod_serra"):
                    dt_p = st.date_input("Data")
                    esp = st.selectbox("Espécie de Tora", ESPECIES_MADEIRA)
                    vol_t = st.number_input("Tora Serrada no Dia (m³)", min_value=0.01)
                    vol_m = st.number_input("Serrado Obtido no Dia (m³)", min_value=0.01)
                    if st.form_submit_button("Salvar Produção"):
                        supabase.table("producao_industrial").insert({"tipo_produto": "Madeira Serrada", "data_producao": dt_p.strftime("%Y-%m-%d"), "especie": esp, "volume_tora": float(vol_t), "volume_serrado": float(vol_m), "cadastrado_por": email_logado}).execute()
                        st.success("Salvo!")
            with c2:
                st.subheader("🤝 Lançar Venda de Serrados")
                with st.form("form_venda_serra"):
                    dt_v = st.date_input("Data Venda")
                    esp_v = st.selectbox("Espécie Vendida", ESPECIES_MADEIRA)
                    vol_v = st.number_input("Volume Vendido (m³)", min_value=0.01)
                    if st.form_submit_button("Lançar Venda"):
                        supabase.table("vendas_serraria").insert({"data_venda": dt_v.strftime("%Y-%m-%d"), "especie": esp_v, "volume_vendido": float(vol_v), "cadastrado_por": email_logado}).execute()
                        st.success("Registado!")
        with aba_dash: render_dashboard_serraria()

    elif menu == "💸 Ordens de Pagamento":
        renderizar_reprovados(email_logado)
        renderizar_solicitacao_pagamento(perfil_usuario)
        
    elif menu == "❌ Registro de Faltas":
        renderizar_registro_faltas("Indústria")


elif perfil_usuario == "Lançamentos Financeiros (Jonas)":
    st.header("🔔 Aprovações Financeiras")
    aba_pend, aba_conc = st.tabs(["⚠️ Pendentes de Aprovação", "📂 Concluídos (Arquivar)"])
    with aba_pend:
        try: pendentes = supabase.table("lancamentos_financeiros").select("*").eq("status_lancamento", "Aprovação Pendente Financeiro").execute().data
        except: pendentes = []
        if not pendentes: st.success("Sem ordens.")
        for p in pendentes:
            v_atual = float(p.get('valor', 0) or 0)
            with st.expander(f"{p.get('categoria', '')} - {p.get('beneficiario', '')} | R$ {v_atual:,.2f}"):
                st.write(f"**Desc:** {p.get('descricao', '')} | **PIX:** {p.get('pix', '')}")
                motivo = st.text_input("Motivo Recusa", key=f"motivo_{p['id']}")
                c1, c2 = st.columns(2)
                if c1.button("✅ Aprovar", key=f"apr_{p['id']}"):
                    supabase.table("lancamentos_financeiros").update({"status_lancamento": "Lançado - Aguardando Pagamento"}).eq("id", p['id']).execute(); st.rerun()
                if c2.button("❌ Reprovar", type="primary", key=f"rep_{p['id']}"):
                    if not motivo: st.error("Escreva o motivo.")
                    else:
                        supabase.table("lancamentos_financeiros").update({"status_lancamento": "Reprovado", "motivo_recusa": motivo}).eq("id", p['id']).execute(); st.rerun()
    with aba_conc:
        try: pagos = supabase.table("lancamentos_financeiros").select("*").eq("status_lancamento", "Pago - Aguardando Arquivamento").execute().data
        except: pagos = []
        for pg in pagos:
            v_atual = float(pg.get('valor', 0) or 0)
            with st.expander(f"✅ R$ {v_atual:,.2f} - {pg.get('beneficiario', '')}"):
                if st.button("Arquivar Lançamento", key=f"arq_{pg['id']}"):
                    supabase.table("lancamentos_financeiros").update({"status_lancamento": "Arquivado"}).eq("id", pg['id']).execute(); st.rerun()


elif perfil_usuario == "Execução de Pagamentos (Matheus)":
    st.header("💳 Execução de Pagamentos")
    try: contas = supabase.table("lancamentos_financeiros").select("*").eq("status_lancamento", "Lançado - Aguardando Pagamento").execute().data
    except: contas = []
    if not contas: st.info("Nenhum pagamento pendente no momento.")
    for c in contas:
        v_atual = float(c.get('valor', 0) or 0)
        with st.expander(f"💰 {c.get('beneficiario', '')} - R$ {v_atual:,.2f} ({c.get('categoria', '')})"):
            st.write(f"**Desc:** {c.get('descricao', '')} | **PIX:** `{c.get('pix', '')}`")
            if c.get('pix') and st.button("👁️ Mostrar QR-Code", key=f"qr_{c['id']}"):
                payload = formata_pix(c.get('pix', ''), v_atual, c.get('beneficiario', ''))
                st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={payload}")
            if st.button("✅ Pagamento Realizado", type="primary", key=f"pag_{c['id']}"):
                supabase.table("lancamentos_financeiros").update({"status_lancamento": "Pago - Aguardando Arquivamento"}).eq("id", c['id']).execute(); st.rerun()


elif perfil_usuario == "Proprietário / Diretoria (Gean)":
    st.header("👑 Painel Executivo (Diretoria)")
    aba_geral, aba_prod, aba_folha, aba_admin = st.tabs(["📊 Visão Geral Operacional", "📈 Dashboards de Produção", "💵 Status Folha", "🛠️ Editor Master"])
    
    with aba_geral:
        try:
            todos_colabs = supabase.table("colaboradores").select("*").execute().data
            todas_despesas = supabase.table("lancamentos_financeiros").select("*").execute().data
            ativos = len([c for c in todos_colabs if c.get('status_fluxo') == "Operação Liberada"])
            total_gasto = sum([float(d.get('valor', 0) or 0) for d in todas_despesas if d.get('status_lancamento') in ["Pago - Aguardando Arquivamento", "Arquivado", "Pago & Concluído"]])
            c1, c2 = st.columns(2)
            c1.metric("Colaboradores Ativos", ativos)
            c2.metric("Despesas Executadas", f"R$ {total_gasto:,.2f}")
        except: st.error("Erro ao carregar dados financeiros.")

    with aba_prod:
        render_dashboard_floresta()
        render_dashboard_serraria()
        render_dashboard_carvoaria()
            
    with aba_folha:
        try: folha = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Folha de Pagamento").execute().data
        except: folha = []
        pendentes = [f for f in folha if f['status_lancamento'] not in ["Pago - Aguardando Arquivamento", "Arquivado", "Pago & Concluído"]]
        if not pendentes: st.success("✅ **Folha quitada integralmente!**")
        else:
            total_pend = sum(float(f.get('valor', 0) or 0) for f in pendentes)
            st.error(f"⚠️ **Total Pendente: R$ {total_pend:,.2f}**")
            st.dataframe([{"Beneficiário": p.get('beneficiario',''), "Valor (R$)": float(p.get('valor',0) or 0), "Status": p.get('status_lancamento','')} for p in pendentes], use_container_width=True)

    with aba_admin:
        st.caption("Ações realizadas aqui apagam os dados permanentemente da base.")
        et1, et2, et3, et4 = st.tabs(["💰 Financeiro", "👥 Funcionários", "🌲 Floresta", "🏭 Indústria"])
        with et1:
            try: todos_lancamentos = supabase.table("lancamentos_financeiros").select("*").order("id", desc=True).execute().data
            except: todos_lancamentos = []
            for lanc in todos_lancamentos:
                v_at = float(lanc.get('valor', 0) or 0)
                with st.expander(f"ID: {lanc['id']} | {lanc.get('categoria','')} | R$ {v_at:.2f}"):
                    if st.button("🗑️ Apagar", key=f"d_fin_{lanc['id']}"):
                        supabase.table("lancamentos_financeiros").delete().eq("id", lanc['id']).execute(); st.rerun()
        with et2:
            try: todos_colabs = supabase.table("colaboradores").select("*").order("id", desc=True).execute().data
            except: todos_colabs = []
            for colab in todos_colabs:
                with st.expander(f"{colab.get('nome_completo','')} | CPF: {colab.get('cpf','')}"):
                    if st.button("🗑️ Apagar", key=f"d_col_{colab['id']}"):
                        supabase.table("colaboradores").delete().eq("id", colab['id']).execute(); st.rerun()
        with et3:
            try: prod_flor = supabase.table("producao_diaria").select("*").order("id", desc=True).limit(20).execute().data
            except: prod_flor = []
            for pf in prod_flor:
                c1, c2 = st.columns([8,2])
                c1.write(f"Data: {pf.get('data_producao')} | Arrastado: {pf.get('volume_arrastado')} | Romaneado: {pf.get('volume_romaneado')}")
                if c2.button("Apagar", key=f"d_pf_{pf['id']}"):
                    supabase.table("producao_diaria").delete().eq("id", pf['id']).execute(); st.rerun()
        with et4:
            try: p_carv = supabase.table("producao_carvao").select("*").order("id", desc=True).limit(20).execute().data
            except: p_carv = []
            for pc in p_carv:
                c1, c2 = st.columns([8,2])
                c1.write(f"Data: {pc.get('data_producao')} | Marca: {pc.get('marca')} | Sacas: {pc.get('quantidade')}")
                if c2.button("Apagar", key=f"d_pc_{pc['id']}"):
                    supabase.table("producao_carvao").delete().eq("id", pc['id']).execute(); st.rerun()
