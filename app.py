import streamlit as st
from supabase import create_client, Client
from streamlit_drawable_canvas import st_canvas
from fpdf import FPDF
from pypdf import PdfWriter, PdfReader
from datetime import datetime
from PIL import Image
import numpy as np
import io
import tempfile
import os
import unicodedata

# Configuração da página
st.set_page_config(page_title="Florestal Operacional", layout="centered", page_icon="🌲")

# ---------------------------------------------------------
# CONEXÃO COM A BASE DE DADOS SUPABASE
# ---------------------------------------------------------
SUPABASE_URL = "https://ekqemmqbgesyvngbiqyk.supabase.co"
SUPABASE_KEY = "sb_publishable_pLuBSE1xQymIoRqONHDJMA_HUZMw23I"

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# Nome do Bucket principal no Supabase
BUCKET_STORAGE = "Funcionarios"

# ---------------------------------------------------------
# FUNÇÃO PARA LIMPEZA DE NOMES DE ARQUIVOS
# ---------------------------------------------------------
def limpar_nome_arquivo(texto):
    """Remove acentos e caracteres especiais para criar nomes de arquivos limpos."""
    nfkd = unicodedata.normalize('NFKD', texto)
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return "".join([c if c.isalnum() or c in "._-" else "_" for c in sem_acento])

# ---------------------------------------------------------
# FUNÇÕES GERADORAS (PIX & PDFs)
# ---------------------------------------------------------

def formata_pix(chave, valor, nome="Colaborador", cidade="Macapa"):
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')[:25].strip()
    cidade = ''.join(c for c in unicodedata.normalize('NFD', cidade) if unicodedata.category(c) != 'Mn')[:15].strip()
    valor_str = f"{valor:.2f}"
    chave = chave.replace(" ", "")
    
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
    
    polynomial = 0x1021
    crc = 0xFFFF
    for char in payload:
        crc ^= (ord(char) << 8)
        for _ in range(8):
            if (crc & 0x8000):
                crc = (crc << 1) ^ polynomial
            else:
                crc = (crc << 1)
            crc &= 0xFFFF
    return payload + f"{crc:04X}"


def gerar_pdf_ficha_epi(nome, cpf, cargo, setor, data_adm, epis_entregues, foto_camera=None, canvas_result=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "FLORESTAL AMAZONIA - TERMO DE ENTREGA DE EPI", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 6, "Conforme Norma Regulamentadora NR-31 / MTE", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "1. DADOS DO COLABORADOR", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"Nome Completo: {nome}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"CPF: {cpf}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Setor: {setor} | Cargo / Funcao: {cargo}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Data de Admissao: {data_adm}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "2. EQUIPAMENTOS DE PROTECAO INDIVIDUAL (EPIs)", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for item in epis_entregues:
        item_limpo = item.replace('ç', 'c').replace('ã', 'a').replace('í', 'i').replace('ó', 'o').replace('á', 'a').replace('ê', 'e')
        pdf.cell(0, 5, f"[ X ] {item_limpo}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "3. TERMO DE COMPROMISSO E RESPONSABILIDADE", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    termo = ("Declaro ter recebido da empresa os Equipamentos de Protecao Individual (EPIs) acima relacionados, "
             "em perfeitas condicoes de uso e conservacao. Comprometo-me a utiliza-los obrigatoriamente durante o exercicio "
             "de minhas funcoes, zelar por sua guarda e conservacao, e comunicar imediatamente ao setor de RH qualquer "
             "extravio ou dano que os torne improprios para uso.")
    pdf.multi_cell(0, 4, termo)
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "4. COMPROVACAO DE ENTREGA (FOTO & ASSINATURA)", border=False, new_x="LMARGIN", new_y="NEXT")
    
    temp_foto_path = None
    temp_sig_path = None
    try:
        if foto_camera is not None:
            foto_bytes = foto_camera.getvalue()
            foto_pil = Image.open(io.BytesIO(foto_bytes)).convert("RGB")
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
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(45, 5, "Foto Registrada", border=False, align="C")
            
        if temp_sig_path:
            x_sig = 110 if temp_foto_path else 15
            pdf.image(temp_sig_path, x=x_sig, y=y_start, w=60, h=30)
            pdf.set_xy(x_sig, y_start + 31)
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(60, 5, "Assinatura do Colaborador", border=False, align="C")
            
        pdf.set_y(y_start + 45)
    except Exception as e:
        st.error(f"⚠️ Erro ao inserir imagens no PDF: {e}")
    finally:
        if temp_foto_path and os.path.exists(temp_foto_path):
            os.remove(temp_foto_path)
        if temp_sig_path and os.path.exists(temp_sig_path):
            os.remove(temp_sig_path)

    pdf.set_font("Helvetica", "I", 8)
    data_hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(0, 5, f"Registro auditado e validado digitalmente em: {data_hoje}", border=False, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def gerar_pdf_cadastro_completo(ficha_epi_bytes, aso_arquivo=None, doc_pessoal_arquivo=None):
    writer = PdfWriter()
    writer.append(io.BytesIO(ficha_epi_bytes))
    
    for arq in [aso_arquivo, doc_pessoal_arquivo]:
        if arq is not None:
            bytes_arq = arq.getvalue()
            if hasattr(arq, 'name') and "pdf" in arq.name.lower():
                try:
                    writer.append(io.BytesIO(bytes_arq))
                except:
                    pass
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
                except:
                    pass
                
    output_io = io.BytesIO()
    writer.write(output_io)
    return output_io.getvalue()


def gerar_pdf_relatorio_auditoria(ativos, total_ativos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "FLORESTAL AMAZONIA - RELATORIO DE AUDITORIA INTERNA (FSC / NR-31)", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 9)
    data_hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(0, 5, f"Data de Emissao: {data_hoje} | Emitido por: Diretoria / Proprietario", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, f"1. SUMARIO EXECUTIVO (Total de Colaboradores Ativos: {total_ativos})", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, "Este relatorio atesta o controlo de conformidade trabalhista, entrega de EPIs, exames admissionais (ASO) e capacitacao obrigatoria de campo conforme as normas de auditoria florestal.")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "2. LISTAGEM E CONFORMIDADE DOS COLABORADORES ATIVOS", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(60, 6, "Nome", border=1)
    pdf.cell(30, 6, "CPF", border=1)
    pdf.cell(50, 6, "Cargo", border=1)
    pdf.cell(30, 6, "Setor", border=1)
    pdf.cell(20, 6, "ASO/EPI", border=1, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "", 9)
    for c in ativos:
        nome_str = str(c.get('nome_completo', ''))[:28]
        pdf.cell(60, 6, nome_str, border=1)
        pdf.cell(30, 6, str(c.get('cpf', '')), border=1)
        pdf.cell(50, 6, str(c.get('cargo', ''))[:22], border=1)
        pdf.cell(30, 6, str(c.get('setor', ''))[:14], border=1)
        status_doc = "OK" if c.get('url_aso') and c.get('url_ficha_pdf') else "Pendente"
        pdf.cell(20, 6, status_doc, border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(15)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, "Assinatura do Proprietario / Auditoria Interna: ___________________________________", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    return bytes(pdf.output())


def gerar_pdf_ordem_pagamento(conta):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "FLORESTAL AMAZONIA - ORDEM DE PAGAMENTO", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    if conta.get('status_lancamento') in ["Pago & Concluído", "Arquivado", "Enviado Contabilidade"]:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(0, 128, 0)
        pdf.cell(0, 10, "[ STATUS: PAGO E EXECUTADO ]", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "1. DADOS DA TRANSACAO", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    
    desc_limpa = str(conta.get('descricao', '')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o').replace('\n', ' | ')
    cat_limpa = str(conta.get('categoria', '')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o')
    banco_saida = str(conta.get('url_comprovante_pago', 'Nao registrado'))
    
    pdf.cell(0, 6, f"ID do Lancamento: {conta.get('id', 'N/A')}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Categoria: {cat_limpa}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Conta de Saida (Banco): {banco_saida}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Valor Executado: R$ {conta.get('valor', 0):.2f}", border=False, new_x="LMARGIN", new_y="NEXT")
    vencimento_br = "/".join(conta.get('data_vencimento', '').split("-")[::-1]) if conta.get('data_vencimento') else 'N/A'
    pdf.cell(0, 6, f"Vencimento Original: {vencimento_br}", border=False, new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Descricao Detalhada / Favorecido (Centro de Custo):", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, desc_limpa)
    
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 9)
    data_hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(0, 5, f"Documento gerado e validado pelo sistema integrado Florestal em: {data_hoje}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(15)
    pdf.cell(0, 5, "Assinatura do Responsavel Financeiro / Contabilidade: ___________________________________", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    return bytes(pdf.output())


def gerar_pdf_fechamento_mensal(mes_referencia, faltas, adiantamentos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, f"FECHAMENTO MENSAL CONSOLIDADO - {mes_referencia}", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "1. REGISTRO DE FALTAS DO PERIODO", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    
    if not faltas:
        pdf.cell(0, 6, "Nenhuma falta registrada e pendente neste periodo.", border=False, new_x="LMARGIN", new_y="NEXT")
    else:
        for f in faltas:
            dt_falta = "/".join(f.get('data_falta', '').split("-")[::-1])
            nome = str(f.get('nome_colaborador', '')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o')
            motivo = str(f.get('observacao', 'Sem justificativa')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o').replace('\n', ' ')
            pdf.cell(0, 6, f"Colaborador: {nome} | Data da Falta: {dt_falta}", border=False, new_x="LMARGIN", new_y="NEXT")
            pdf.multi_cell(0, 5, f"   Motivo / Obs: {motivo}")
            pdf.ln(2)
            
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "2. ADIANTAMENTOS SALARIAIS EXECUTADOS", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    
    total_adiantamentos = 0
    if not adiantamentos:
        pdf.cell(0, 6, "Nenhum adiantamento executado neste periodo.", border=False, new_x="LMARGIN", new_y="NEXT")
    else:
        for a in adiantamentos:
            vlr = a.get('valor', 0)
            total_adiantamentos += vlr
            desc = str(a.get('descricao', '')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o').replace('\n', ' ')
            pdf.multi_cell(0, 6, f"- R$ {vlr:.2f} | Detalhes: {desc}")
            pdf.ln(1)
            
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 10, f"TOTAL GERAL DE ADIANTAMENTOS: R$ {total_adiantamentos:.2f}", border=False, new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(15)
    pdf.set_font("Helvetica", "I", 9)
    data_hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(0, 5, f"Documento de fechamento gerado e validado pelo sistema em: {data_hoje}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.cell(0, 5, "Assinatura do Departamento Financeiro: ___________________________________", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    
    return bytes(pdf.output())


def gerar_pdf_resumo_acerto(colab, faltas, adiantamentos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "FLORESTAL AMAZONIA - RESUMO DE ACERTO CONTABIL", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "1. DADOS DO COLABORADOR DESLIGADO/INAPTO", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    nome = str(colab.get('nome_completo', '')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o')
    cargo = str(colab.get('cargo', '')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o')
    motivo = str(colab.get('motivo_desligamento', 'Nao informado')).replace('ç','c').replace('ã','a').replace('í','i').replace('á','a').replace('é','e').replace('õ','o').replace('\n', ' ')
    
    pdf.cell(0, 6, f"Nome Completo: {nome}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"CPF: {colab.get('cpf', '')}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Cargo/Setor: {cargo} - {colab.get('setor', '')}", border=False, new_x="LMARGIN", new_y="NEXT")
    
    data_adm = "/".join(colab.get('data_admissao', '').split("-")[::-1]) if colab.get('data_admissao') else ''
    pdf.cell(0, 6, f"Data de Admissao Original: {data_adm}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Status no Sistema: {colab.get('status_fluxo', '')}", border=False, new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(3)
    pdf.multi_cell(0, 5, f"Motivo do Desligamento / Inaptidao: {motivo}")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "2. RESUMO DE FALTAS (HISTORICO DO COLABORADOR)", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    
    if not faltas:
        pdf.cell(0, 6, "Nenhuma falta registrada no sistema.", border=False, new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 6, f"Total de ocorrencias (dias): {len(faltas)}", border=False, new_x="LMARGIN", new_y="NEXT")
        for f in faltas:
            dt_falta = "/".join(f.get('data_falta', '').split("-")[::-1])
            pdf.cell(0, 6, f" - Data: {dt_falta}", border=False, new_x="LMARGIN", new_y="NEXT")
            
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "3. RESUMO DE ADIANTAMENTOS SALARIAIS E VALES", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    
    total_adiant = 0
    if not adiantamentos:
        pdf.cell(0, 6, "Nenhum adiantamento ou vale registrado.", border=False, new_x="LMARGIN", new_y="NEXT")
    else:
        for a in adiantamentos:
            vlr = a.get('valor', 0)
            total_adiant += vlr
            dt_a = "/".join(a.get('data_vencimento', '').split("-")[::-1]) if a.get('data_vencimento') else ''
            pdf.cell(0, 6, f" - Em {dt_a}: R$ {vlr:.2f}", border=False, new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 10, f"TOTAL DE ADIANTAMENTOS A DESCONTAR NO ACERTO: R$ {total_adiant:.2f}", border=False, new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(15)
    pdf.set_font("Helvetica", "I", 9)
    data_hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.cell(0, 5, f"Documento gerado automaticamente pela Engenharia/RH em: {data_hoje}", border=False, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# ---------------------------------------------------------
# PAINEL DE COLABORADORES EM OPERAÇÃO
# ---------------------------------------------------------
def renderizar_painel_colaboradores_ativos():
    st.markdown("---")
    st.subheader("👥 Colaboradores em Operação (Ativos)")
    st.caption("Visão geral de todos os colaboradores com operação liberada na empresa.")
    
    try:
        ativos = supabase.table("colaboradores").select("*").eq("status_fluxo", "Operação Liberada").execute().data
    except Exception as e:
        ativos = []
        st.error(f"Erro ao buscar colaboradores: {e}")
        
    if not ativos:
        st.info("Nenhum colaborador com status de Operação Liberada no momento.")
        return

    total_ativos = len(ativos)
    setores_contagem = {}
    cargos_contagem = {}
    
    for c in ativos:
        setor = c.get('setor', 'Outros')
        cargo = c.get('cargo', 'Não definido')
        setores_contagem[setor] = setores_contagem.get(setor, 0) + 1
        cargos_contagem[cargo] = cargos_contagem.get(cargo, 0) + 1
        
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.metric("Total de Ativos", total_ativos)
    with col_t2:
        resumo_setores = " | ".join([f"{k}: {v}" for k, v in setores_contagem.items()])
        st.info(f"**Por Setor:** {resumo_setores}")
        
    with st.expander("📊 Ver Resumo por Função / Cargo"):
        for cargo_nome, qtd in sorted(cargos_contagem.items(), key=lambda x: x[1], reverse=True):
            st.write(f"- **{cargo_nome}:** {qtd} colaborador(es)")
            
    st.write("📋 **Lista Completa de Ativos (com rolagem):**")
    
    dados_tabela = []
    for idx, c in enumerate(ativos, 1):
        dt_adm_br = "/".join(c.get('data_admissao', '').split("-")[::-1]) if c.get('data_admissao') else 'N/A'
        dados_tabela.append({
            "Nº": idx,
            "Nome Completo": c.get('nome_completo'),
            "CPF": c.get('cpf'),
            "Cargo": c.get('cargo'),
            "Setor": c.get('setor'),
            "Admissão": dt_adm_br,
            "PIX": c.get('chave_pix', 'Não cad.'),
            "ASO": "Ver ASO" if c.get('url_aso') else "Não anexo",
            "Doc. Pessoal": "Ver Doc" if c.get('url_documento_pessoal') else "Não anexo"
        })
        
    st.dataframe(dados_tabela, use_container_width=True, hide_index=True)


# ---------------------------------------------------------
# INTERFACE PRINCIPAL
# ---------------------------------------------------------
st.title("🌲 Florestal Operacional")
st.caption("Sistema Integrado de Operação & Financeiro")

perfil_usuario = st.sidebar.selectbox(
    "Selecione o seu Perfil:",
    ["Proprietário / Diretoria (Gean)", "RH Operacional (Maria / Felipe)", "Engenharia Florestal (Jean Gustavo)", "Lançamentos Financeiros (Jonas)", "Execução de Pagamentos (Matheus)"]
)
st.sidebar.divider()
st.sidebar.info(f"Utilizador ativo: **{perfil_usuario}**")

# ---------------------------------------------------------
# 0. PROPRIETÁRIO / DIRETORIA (GEAN)
# ---------------------------------------------------------
if perfil_usuario == "Proprietário / Diretoria (Gean)":
    st.header("👑 Painel Executivo & Auditoria (Diretoria)")
    st.caption("Bem-vindo, Gean. Visão completa de fiscalização, conformidade e relatórios da operação.")
    
    try:
        todos_colabs = supabase.table("colaboradores").select("*").execute().data
        todas_despesas = supabase.table("lancamentos_financeiros").select("*").execute().data
        todas_faltas = supabase.table("registro_faltas").select("*").execute().data
        producao_data = supabase.table("producao_diaria").select("*").execute().data
    except:
        todos_colabs, todas_despesas, todas_faltas, producao_data = [], [], [], []
        
    ativos_gean = [c for c in todos_colabs if c.get('status_fluxo') == "Operação Liberada"]
    pendentes_gean = [c for c in todos_colabs if c.get('status_fluxo') in ["Aguardando Treinamento", "Em Treinamento"]]
    desligados_gean = [c for c in todos_colabs if c.get('status_fluxo') in ["Não Habilitado", "Desligamento da empresa", "Acerto Concluído"]]
    
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("👥 Colaboradores Ativos", len(ativos_gean))
    with kpi2:
        st.metric("⏳ Em Treinamento / Fila", len(pendentes_gean))
    with kpi3:
        st.metric("🚪 Desligados / Acertos", len(desligados_gean))
    with kpi4:
        total_gasto = sum([d.get('valor', 0) for d in todas_despesas if d.get('status_lancamento') in ["Pago & Concluído", "Arquivado"]])
        st.metric("💰 Despesas Executadas", f"R$ {total_gasto:,.2f}")
        
    st.divider()
    
    aba_audit, aba_prod_exec, aba_func_geral, aba_fin_geral = st.tabs(["🛡️ Auditoria (FSC)", "📊 Produção & Eficiência", "📋 Todos os Funcionários", "📊 Visão Financeira"])
    
    with aba_audit:
        st.subheader("Relatório de Auditoria Interna e Conformidade")
        st.caption("Gere relatórios executivos em PDF para auditorias do FSC e controle de medicina/segurança do trabalho.")
        
        if st.button("📄 Gerar Relatório de Auditoria em PDF"):
            if not ativos_gean:
                st.warning("Não há colaboradores ativos para gerar o relatório.")
            else:
                pdf_audit_bytes = gerar_pdf_relatorio_auditoria(ativos_gean, len(ativos_gean))
                st.success("Relatório de auditoria gerado com sucesso!")
                st.download_button("📥 Baixar Relatório de Auditoria (PDF)", pdf_audit_bytes, file_name=f"Relatorio_Auditoria_FSC_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf")
                
        st.write("---")
        st.write("📌 **Checklist de Documentação Obrigatória (Auditados na Nuvem):**")
        dados_audit = []
        for c in ativos_gean:
            tem_epi = "Sim" if c.get('url_ficha_pdf') else "Pendente"
            tem_aso = "Sim" if c.get('url_aso') else "Pendente"
            tem_doc = "Sim" if c.get('url_documento_pessoal') else "Pendente"
            dados_audit.append({
                "Nome": c.get('nome_completo'),
                "CPF": c.get('cpf'),
                "Setor": c.get('setor'),
                "Ficha EPI": tem_epi,
                "ASO Médico": tem_aso,
                "Doc. Pessoal": tem_doc
            })
        if dados_audit:
            st.dataframe(dados_audit, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum colaborador ativo cadastrado para auditoria.")

    with aba_prod_exec:
        st.subheader("📈 Desempenho Operacional e Produção da Safra")
        st.caption("Resumo diário, mensal e acumulado de eficiência de abate e romaneio florestal.")
        
        if not producao_data:
            st.info("Nenhum registo de produção diária encontrado. Cadastre a produção na aba de Engenharia.")
        else:
            total_vol_abatido = sum([float(p.get('volume_abatido_m3', 0) or 0) for p in producao_data])
            total_vol_romaneado = sum([float(p.get('volume_romaneado_m3', 0) or 0) for p in producao_data])
            total_arv_abatidas = sum([int(p.get('arvores_abatidas', 0) or 0) for p in producao_data])
            total_arv_romaneadas = sum([int(p.get('arvores_romaneadas', 0) or 0) for p in producao_data])
            total_dias = len(producao_data)
            media_diaria_abat = total_vol_abatido / total_dias if total_dias > 0 else 0
            
            kp1, kp2, kp3 = st.columns(3)
            with kp1:
                st.metric("🌲 Vol. Total Abatido (Safra)", f"{total_vol_abatido:,.3f} m³")
            with kp2:
                st.metric("🪵 Vol. Total Romaneado (Safra)", f"{total_vol_romaneado:,.3f} m³")
            with kp3:
                st.metric("⚡ Média Diária Abate", f"{media_diaria_abat:,.3f} m³/dia")
                
            st.divider()
            
            # --- PRODUÇÃO MENSAL ---
            st.write("📅 **Resumo da Produção Mensal:**")
            mensal_dict = {}
            for p in producao_data:
                dt_str = p.get('data_producao', '')
                if dt_str and len(dt_str) >= 7:
                    ano_mes = dt_str[:7] # 'YYYY-MM'
                    partes = ano_mes.split('-')
                    mes_ano_fmt = f"{partes[1]}/{partes[0]}" if len(partes) == 2 else ano_mes
                else:
                    mes_ano_fmt = "Desconhecido"
                    
                if mes_ano_fmt not in mensal_dict:
                    mensal_dict[mes_ano_fmt] = {
                        "arv_abat": 0, "vol_abat": 0.0,
                        "arv_rom": 0, "vol_rom": 0.0,
                        "dias": 0
                    }
                mensal_dict[mes_ano_fmt]["arv_abat"] += int(p.get('arvores_abatidas', 0) or 0)
                mensal_dict[mes_ano_fmt]["vol_abat"] += float(p.get('volume_abatido_m3', 0) or 0)
                mensal_dict[mes_ano_fmt]["arv_rom"] += int(p.get('arvores_romaneadas', 0) or 0)
                mensal_dict[mes_ano_fmt]["vol_rom"] += float(p.get('volume_romaneado_m3', 0) or 0)
                mensal_dict[mes_ano_fmt]["dias"] += 1
                
            tabela_mensal = []
            for mes_ano, vals in sorted(mensal_dict.items(), reverse=True):
                tabela_mensal.append({
                    "Mês / Ano": mes_ano,
                    "Dias Trab.": vals["dias"],
                    "Árv. Abatidas": vals["arv_abat"],
                    "Vol. Abatido (m³)": f"{vals['vol_abat']:,.3f}",
                    "Árv. Romaneadas": vals["arv_rom"],
                    "Vol. Romaneado (m³)": f"{vals['vol_rom']:,.3f}"
                })
            st.dataframe(tabela_mensal, use_container_width=True, hide_index=True)
            
            st.divider()
            st.write("📋 **Histórico Diário de Campo:**")
            tabela_prod = []
            for p in sorted(producao_data, key=lambda x: x.get('data_producao', ''), reverse=True):
                dt_fmt = "/".join(p.get('data_producao', '').split("-")[::-1])
                tabela_prod.append({
                    "Data": dt_fmt,
                    "Árvores Abatidas": p.get('arvores_abatidas'),
                    "Vol. Abatido (m³)": f"{float(p.get('volume_abatido_m3', 0) or 0):,.3f}",
                    "Árvores Romaneadas": p.get('arvores_romaneadas'),
                    "Vol. Romaneado (m³)": f"{float(p.get('volume_romaneado_m3', 0) or 0):,.3f}"
                })
            st.dataframe(tabela_prod, use_container_width=True, hide_index=True)

    with aba_func_geral:
        st.subheader("Base Completa de Colaboradores")
        if not todos_colabs:
            st.info("Nenhum colaborador registado no sistema.")
        else:
            tabela_geral = [{"Nome": c.get('nome_completo'), "CPF": c.get('cpf'), "Cargo": c.get('cargo'), "Setor": c.get('setor'), "Status": c.get('status_fluxo')} for c in todos_colabs]
            st.dataframe(tabela_geral, use_container_width=True, hide_index=True)

    with aba_fin_geral:
        st.subheader("Panorama de Lançamentos Financeiros")
        if not todas_despesas:
            st.info("Nenhum lançamento financeiro registado.")
        else:
            tabela_fin = [{"ID": d.get('id'), "Categoria": d.get('categoria'), "Valor (R$)": f"R$ {d.get('valor', 0):.2f}", "Status": d.get('status_lancamento')} for d in todas_despesas]
            st.dataframe(tabela_fin, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# 1. RH OPERACIONAL (MARIA)
# ---------------------------------------------------------
elif perfil_usuario == "RH Operacional (Maria / Felipe)":
    st.header("📋 Recursos Humanos")
    
    desligamentos_pendentes = supabase.table("colaboradores").select("id").in_("status_fluxo", ["Não Habilitado", "Desligamento da empresa"]).execute().data
    if desligamentos_pendentes and len(desligamentos_pendentes) > 0:
        st.error(f"🚨 **ALERTA DE DESLIGAMENTO:** Você tem {len(desligamentos_pendentes)} processo(s) pendente(s) aguardando envio para a Contabilidade! Acesse a aba '🚪 Desligamentos e Acertos'.")
    
    aba_cadastro, aba_desligamentos, aba_folha_rh, aba_ativos_rh = st.tabs(["🆕 Cadastro & EPI", "🚪 Desligamentos e Acertos", "💵 Envio de Holerites", "👥 Colaboradores em Operação"])
    
    with aba_cadastro:
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

        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Nome Completo do Colaborador")
            cpf = st.text_input("CPF")
            chave_pix_cad = st.text_input("Chave PIX do Colaborador")
            data_adm = st.date_input("Data de Admissão")
            
        with col2:
            setor_escolhido = st.selectbox("Setor Operacional", list(EPI_POR_SETOR.keys()))
            cargo_escolhido = st.selectbox("Cargo / Função", list(EPI_POR_SETOR[setor_escolhido].keys()))
        
        st.divider()
        st.subheader("🏥 Digitalização de Documentos (Câmera)")
        
        aso_foto_cam = None
        usar_cam_aso = st.checkbox("📸 Digitalizar ASO (Exame Admissional) com a Câmera")
        if usar_cam_aso:
            aso_foto_cam = st.camera_input("Aponte para o ASO físico e clique em tirar foto", key="cam_aso_input")
            if aso_foto_cam:
                st.success("ASO digitalizado com sucesso!")
                
        doc_foto_cam = None
        usar_cam_doc = st.checkbox("📸 Digitalizar Documento Pessoal (CNH / RG / CPF) com a Câmera")
        if usar_cam_doc:
            doc_foto_cam = st.camera_input("Aponte para o Documento Pessoal e clique em tirar foto", key="cam_doc_input")
            if doc_foto_cam:
                st.success("Documento Pessoal digitalizado com sucesso!")
        
        st.divider()
        st.subheader(f"🪖 Kit de EPI Obrigatório (PGR): {cargo_escolhido}")
        
        epis_exigidos = EPI_POR_SETOR[setor_escolhido][cargo_escolhido]
        epis_marcados = []
        col_epi1, col_epi2 = st.columns(2)
        for i, epi in enumerate(epis_exigidos):
            if (col_epi1 if i % 2 == 0 else col_epi2).checkbox(epi, key=f"epi_{i}"):
                epis_marcados.append(epi)
        
        todos_epis_checados = len(epis_marcados) == len(epis_exigidos)
        
        st.divider()
        conduta = st.checkbox("Código de Conduta & Regras de Segurança Lidas e Aceites")
        
        st.write("📷 **Registo de Foto do Colaborador**")
        foto_capturada = None
        if "foto_arquivo_temp" not in st.session_state:
            st.session_state.foto_arquivo_temp = None

        ativar_cam = st.checkbox("Ligar Câmera para Foto do Rosto")
        if ativar_cam:
            foto_input_raw = st.camera_input("Clique abaixo para tirar a foto do colaborador", key="cam_rosto")
            if foto_input_raw is not None:
                st.session_state.foto_arquivo_temp = foto_input_raw
                st.success("Foto capturada com sucesso!")

        if st.session_state.foto_arquivo_temp is not None:
            st.image(st.session_state.foto_arquivo_temp, width=200, caption="Foto Guardada")
            foto_capturada = st.session_state.foto_arquivo_temp

        st.divider()
        st.subheader("✍ Assinatura Digital")
        canvas_result = st_canvas(fill_color="rgba(255, 255, 255, 0)", stroke_width=2, stroke_color="#000000", background_color="#F0F2F6", height=150, drawing_mode="freedraw", key="canvas", update_streamlit=True, return_image_data=True)

        if st.button("Cadastrar e Gerar Cadastro"):
            tem_foto = foto_capturada is not None
            tem_assinatura = canvas_result is not None and canvas_result.json_data and len(canvas_result.json_data.get("objects", [])) > 0

            if not (nome.strip() and cpf.strip() and cargo_escolhido.strip()):
                st.error("Preencha todos os dados pessoais do colaborador (Nome, CPF).")
            elif not conduta:
                st.error("O Código de Conduta precisa ser confirmado.")
            elif not todos_epis_checados:
                st.error(f"Todos os {len(epis_exigidos)} itens do kit precisam ser confirmados!")
            elif not (tem_foto or tem_assinatura):
                st.error("Tire uma Foto ou colha a Assinatura Digital antes de finalizar.")
            else:
                setor_db = "Colheita" if setor_escolhido == "Floresta" else ("Indústria" if setor_escolhido == "Indústria / Carvoaria" else setor_escolhido)
                
                pdf_ficha_epi_bytes = gerar_pdf_ficha_epi(nome.strip(), cpf.strip(), cargo_escolhido, setor_escolhido, data_adm.strftime("%d/%m/%Y"), epis_marcados, foto_capturada, canvas_result)
                pdf_cadastro_completo = gerar_pdf_cadastro_completo(pdf_ficha_epi_bytes, aso_foto_cam, doc_foto_cam)
                
                nome_limpo = limpar_nome_arquivo(nome.strip())
                cpf_limpo = cpf.strip().replace('.', '').replace('-', '')
                pasta_funcionario = f"{nome_limpo}_{cpf_limpo}"
                
                nome_arquivo_epi = f"{pasta_funcionario}/Ficha_Epi/Termo_EPI.pdf"
                try:
                    supabase.storage.from_(BUCKET_STORAGE).upload(nome_arquivo_epi, pdf_ficha_epi_bytes, {"content-type": "application/pdf", "upsert": "true"})
                except:
                    pass
                url_pdf = supabase.storage.from_(BUCKET_STORAGE).get_public_url(nome_arquivo_epi)
                
                url_aso_final = ""
                if aso_foto_cam is not None:
                    try:
                        nome_arquivo_aso = f"{pasta_funcionario}/Aso/Exame_Admissional.jpg"
                        supabase.storage.from_(BUCKET_STORAGE).upload(nome_arquivo_aso, aso_foto_cam.getvalue(), {"upsert": "true"})
                        url_aso_final = supabase.storage.from_(BUCKET_STORAGE).get_public_url(nome_arquivo_aso)
                    except:
                        pass

                url_doc_final = ""
                if doc_foto_cam is not None:
                    try:
                        nome_arquivo_doc = f"{pasta_funcionario}/Documentos_Pessoais/Documento_Pessoal.jpg"
                        supabase.storage.from_(BUCKET_STORAGE).upload(nome_arquivo_doc, doc_foto_cam.getvalue(), {"upsert": "true"})
                        url_doc_final = supabase.storage.from_(BUCKET_STORAGE).get_public_url(nome_arquivo_doc)
                    except:
                        pass
                
                try:
                    supabase.table("colaboradores").insert({
                        "nome_completo": nome.strip(), "cpf": cpf.strip(), "cargo": cargo_escolhido, "setor": setor_db, 
                        "data_admissao": data_adm.strftime("%Y-%m-%d"), "ficha_epi_assinada": True, "codigo_conduta_lido": conduta,
                        "status_fluxo": "Aguardando Treinamento", "url_ficha_pdf": url_pdf, "chave_pix": chave_pix_cad.strip(), 
                        "url_aso": url_aso_final, "url_documento_pessoal": url_doc_final
                    }).execute()
                    st.success(f"Colaborador {nome} registado com sucesso e documentos arquivados!")
                    st.session_state.foto_arquivo_temp = None
                    st.download_button("📥 Baixar Cadastro Realizado (PDF)", pdf_cadastro_completo, f"Cadastro_{nome_limpo}.pdf", "application/pdf")
                except Exception as err:
                    st.error("O CPF já está registado." if "23505" in str(err) else f"Erro: {err}")
    
    with aba_desligamentos:
        st.subheader("Processos de Desligamento / Acerto Contábil")
        st.caption("Colaboradores que não passaram no treinamento ou foram demitidos.")
        
        desligados = supabase.table("colaboradores").select("*").in_("status_fluxo", ["Não Habilitado", "Desligamento da empresa"]).execute().data
        
        if not desligados:
            st.info("Nenhum processo de desligamento pendente no momento.")
        else:
            for colab in desligados:
                with st.expander(f"⚠️ {colab['nome_completo']} - Status: {colab['status_fluxo']}"):
                    st.write(f"**CPF:** {colab['cpf']}")
                    st.write(f"**Motivo Registrado:** {colab.get('motivo_desligamento', 'Sem observações.')}")
                    
                    if colab.get('url_aviso_desligamento'):
                        st.write(f"📄 **Aviso/Documento de Desligamento:** [Visualizar Anexo]({colab['url_aviso_desligamento']})")
                    
                    st.divider()
                    st.write("Baixe o resumo financeiro para enviar à Contabilidade:")
                    
                    faltas_colab = supabase.table("registro_faltas").select("*").eq("id_colaborador", colab['id']).execute().data
                    nome_limpo = colab['nome_completo'].strip()
                    adiantamentos_todos = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Adiantamento Salarial").execute().data
                    adiantamentos_colab = [a for a in adiantamentos_todos if nome_limpo.lower() in a['descricao'].lower()]
                    
                    pdf_acerto = gerar_pdf_resumo_acerto(colab, faltas_colab, adiantamentos_colab)
                    nome_colab_limpo = limpar_nome_arquivo(colab['nome_completo'])
                    st.download_button(label="📄 Baixar Resumo para Acerto (PDF)", data=pdf_acerto, file_name=f"Resumo_Acerto_{nome_colab_limpo}.pdf", mime="application/pdf", key=f"dl_acerto_{colab['id']}")
                    
                    st.write("---")
                    if st.button("✅ Confirmar Envio p/ Contabilidade e Arquivar", key=f"arq_rh_{colab['id']}"):
                        supabase.table("colaboradores").update({"status_fluxo": "Acerto Concluído"}).eq("id", colab['id']).execute()
                        st.success("Acerto arquivado com sucesso!")
                        st.rerun()

    with aba_folha_rh:
        st.subheader("Envio de Holerites para Pagamento")
        st.caption("Insira o holerite da contabilidade. O mês e o PIX do colaborador são preenchidos automaticamente.")
        
        ativos_rh = supabase.table("colaboradores").select("id, nome_completo, cpf, cargo, setor, chave_pix").eq("status_fluxo", "Operação Liberada").execute().data
        if not ativos_rh:
            st.warning("Nenhum colaborador ativo encontrado.")
        else:
            opcoes_folha = {f"{c['nome_completo']} ({c['cargo']})": c for c in ativos_rh}
            colab_sel_str = st.selectbox("Selecionar Colaborador:", list(opcoes_folha.keys()))
            colab_folha = opcoes_folha[colab_sel_str]
            
            mes_atual_sugerido = datetime.now().strftime("%B/%Y").capitalize()
            mes_ref = st.text_input("Mês de Referência", value=mes_atual_sugerido, key="mes_ref_input_folha")
            
            valor_liq = st.number_input("Valor Líquido (R$)", min_value=1.0, value=1500.0)
            
            pix_sugerido = colab_folha.get('chave_pix', '') or ''
            pix_folha = st.text_input("Chave PIX do Colaborador", value=pix_sugerido, key=f"pix_folha_{colab_folha['id']}")
            
            holerite_pdf = st.file_uploader("Anexar Holerite em PDF", type=["pdf"])
            
            if st.button("Gerar Ordem de Pagamento de Folha"):
                if not pix_folha.strip() or not holerite_pdf:
                    st.error("⚠️ A Chave PIX e o anexo do Holerite em PDF são obrigatórios!")
                else:
                    try:
                        nome_colab_limpo = limpar_nome_arquivo(colab_folha['nome_completo'])
                        cpf_limpo = str(colab_folha.get('cpf', '')).replace('.', '').replace('-', '')
                        pasta_funcionario = f"{nome_colab_limpo}_{cpf_limpo}"
                        
                        nome_hol = f"{pasta_funcionario}/Holerites/Holerite_{mes_ref.replace('/','_')}.pdf"
                        supabase.storage.from_(BUCKET_STORAGE).upload(nome_hol, holerite_pdf.getvalue(), {"upsert": "true"})
                        url_hol = supabase.storage.from_(BUCKET_STORAGE).get_public_url(nome_hol)
                    except:
                        url_hol = ""
                        
                    desc_folha = f"Folha de Pagamento - {colab_folha['nome_completo']} | Ref: {mes_ref} | Centro de Custo: {colab_folha['setor']} | PIX: {pix_folha} | Holerite: {url_hol}"
                    
                    supabase.table("lancamentos_financeiros").insert({
                        "descricao": desc_folha,
                        "categoria": "Folha de Pagamento",
                        "valor": valor_liq,
                        "data_vencimento": datetime.now().strftime("%Y-%m-%d"),
                        "status_lancamento": "Aprovação Pendente Folha"
                    }).execute()
                    st.success("✅ Holerite guardado na pasta do colaborador e enviado para a gestão financeira!")

    with aba_ativos_rh:
        renderizar_painel_colaboradores_ativos()

# ---------------------------------------------------------
# 2. ENGENHARIA FLORESTAL (JEAN)
# ---------------------------------------------------------
elif perfil_usuario == "Engenharia Florestal (Jean Gustavo)":
    st.header("🌲 Gestão Operacional de Equipes")
    menu_operacoes = st.radio("Selecione a Ação:", ["🚜 Treinamentos", "💸 Diárias e Adiantamentos", "❌ Registro de Faltas", "🚪 Desligamento (Demissão)", "📊 Produção Diária", "👥 Colaboradores em Operação"], horizontal=True)
    st.divider()

    if menu_operacoes == "🚜 Treinamentos":
        st.subheader("Gestão de Treinamentos e Liberação para Operação")
        
        pendentes = supabase.table("colaboradores").select("*").in_("status_fluxo", ["Aguardando Treinamento", "Em Treinamento"]).execute().data
        aba_prog, aba_extemp = st.tabs(["📅 Programado (Início de Safra)", "⏱️ Extemporâneo (Meio de Safra)"])
        
        with aba_prog:
            st.caption("Para turmas formadas no início da operação com certificado padrão coletivo.")
            lista_prog = [c for c in pendentes if c['status_fluxo'] == "Aguardando Treinamento"]
            if not lista_prog:
                st.info("Nenhum colaborador aguardando treinamento programado.")
            for colab in lista_prog:
                with st.expander(f"📌 {colab['nome_completo']} - {colab['cargo']}"):
                    st.write(f"**CPF:** {colab['cpf']} | **Setor:** {colab['setor']}")
                    cert_prog = st.file_uploader("Anexar Certificado de Conclusão (PDF)", type=["pdf"], key=f"cert_prog_{colab['id']}")
                    
                    if st.button("Validar Certificado e Liberar para Operação", key=f"lib_prog_{colab['id']}"):
                        if cert_prog is not None:
                            nome_colab_limpo = limpar_nome_arquivo(colab['nome_completo'])
                            cpf_limpo = str(colab.get('cpf', '')).replace('.', '').replace('-', '')
                            pasta_funcionario = f"{nome_colab_limpo}_{cpf_limpo}"
                            
                            nome_arq = f"{pasta_funcionario}/Certificado_Treinamento/Certificado.pdf"
                            try:
                                supabase.storage.from_(BUCKET_STORAGE).upload(nome_arq, cert_prog.getvalue(), {"content-type": "application/pdf", "upsert": "true"})
                                url_cert = supabase.storage.from_(BUCKET_STORAGE).get_public_url(nome_arq)
                            except:
                                url_cert = ""
                            
                            supabase.table("colaboradores").update({"status_fluxo": "Operação Liberada", "url_certificado": url_cert}).eq("id", colab['id']).execute()
                            st.success("Colaborador liberado! Certificado arquivado na pasta do colaborador."); st.rerun()
                        else:
                            st.error("⚠️ Anexe o certificado em PDF antes de liberar o colaborador.")

        with aba_extemp:
            st.caption("Para colaboradores contratados no meio da safra. Requer 2 dias de acompanhamento e prova.")
            if not pendentes:
                st.info("Nenhum colaborador nesta esteira.")
            for colab in pendentes:
                with st.expander(f"📌 {colab['nome_completo']} - {colab['cargo']}  [{colab['status_fluxo']}]"):
                    st.write(f"**CPF:** {colab['cpf']} | **Setor:** {colab['setor']}")
                    
                    if colab['status_fluxo'] == "Aguardando Treinamento":
                        st.info("📋 **Dia 1:** Entrega de material, dúvidas com engenheiro e acompanhamento visual da equipe prática.")
                        if st.button("Iniciar Treinamento Extemporâneo (Mudar Status)", key=f"init_ext_{colab['id']}"):
                            supabase.table("colaboradores").update({"status_fluxo": "Em Treinamento"}).eq("id", colab['id']).execute()
                            st.success("Treinamento iniciado! O funcionário agora está no período de avaliação."); st.rerun()
                            
                    elif colab['status_fluxo'] == "Em Treinamento":
                        st.warning("⏱️ **Dia 2:** Avaliação Assistida. O gerente deve dar o aval para a prova.")
                        nota = st.number_input("Nota da Prova Final (0 a 100)", min_value=0, max_value=100, value=0, key=f"nota_{colab['id']}")
                        
                        if nota >= 70:
                            st.success("✅ Aprovado! Nota igual ou superior a 70 pontos.")
                            cert_ext = st.file_uploader("Anexar Certificado de Conclusão (PDF)", type=["pdf"], key=f"cert_ext_{colab['id']}")
                            if st.button("Anexar Certificado e Liberar para Operação", key=f"lib_ext_{colab['id']}"):
                                if cert_ext:
                                    nome_colab_limpo = limpar_nome_arquivo(colab['nome_completo'])
                                    cpf_limpo = str(colab.get('cpf', '')).replace('.', '').replace('-', '')
                                    pasta_funcionario = f"{nome_colab_limpo}_{cpf_limpo}"
                                    
                                    nome_arq = f"{pasta_funcionario}/Certificado_Treinamento/Certificado.pdf"
                                    try:
                                        supabase.storage.from_(BUCKET_STORAGE).upload(nome_arq, cert_ext.getvalue(), {"content-type": "application/pdf", "upsert": "true"})
                                        url_cert = supabase.storage.from_(BUCKET_STORAGE).get_public_url(nome_arq)
                                    except:
                                        url_cert = ""
                                        
                                    supabase.table("colaboradores").update({"status_fluxo": "Operação Liberada", "url_certificado": url_cert}).eq("id", colab['id']).execute()
                                    st.success("Colaborador aprovado e liberado para a operação!"); st.rerun()
                                else:
                                    st.error("⚠️ Gere e anexe o certificado em PDF para finalizar a liberação.")
                        else:
                            if nota > 0:
                                st.error("❌ Reprovado. A nota precisa ser igual ou maior que 70 para emissão do certificado.")
                                st.divider()
                                motivo_inaptidao = st.text_area("Justificativa técnica da Inaptidão / Reprovação:", key=f"motivo_inap_{colab['id']}")
                                if st.button("Confirmar Dispensa (Inapto)", key=f"dispensa_{colab['id']}"):
                                    if not motivo_inaptidao.strip():
                                        st.error("⚠️ Escreva a justificativa antes de dispensar o colaborador.")
                                    else:
                                        supabase.table("colaboradores").update({"status_fluxo": "Não Habilitado", "motivo_desligamento": motivo_inaptidao}).eq("id", colab['id']).execute()
                                        st.success("Colaborador considerado Não Habilitado. O perfil foi devolvido ao RH para acerto."); st.rerun()

    elif menu_operacoes == "💸 Diárias e Adiantamentos":
        st.subheader("Solicitação de Pagamentos")
        aptos = supabase.table("colaboradores").select("id, nome_completo, cpf, cargo, setor, chave_pix").eq("status_fluxo", "Operação Liberada").execute().data
        if not aptos:
            st.warning("Nenhum colaborador apto/ativo encontrado na base de dados.")
        else:
            tipo_pagamento = st.radio("Tipo de ordem:", ["Diária", "Adiantamento"], horizontal=True)
            opcoes_colab = {f"{c['nome_completo']} ({c['cargo']})": c for c in aptos}
            dados_colab = opcoes_colab[st.selectbox("Colaborador:", list(opcoes_colab.keys()))]
            
            col1, col2 = st.columns(2)
            with col1:
                if tipo_pagamento == "Diária":
                    qtd = st.number_input("Quantidade de Diárias", min_value=1, value=1)
                    vlr_un = st.number_input("Valor Unitário (R$)", min_value=0.0, value=50.0)
                    vlr_tot = qtd * vlr_un
                    st.info(f"Valor Total: R$ {vlr_tot:.2f}")
                else:
                    vlr_tot = st.number_input("Valor do Adiantamento (R$)", min_value=1.0, value=100.0)
            with col2:
                dt_pag = st.date_input("Data para Pagamento")
                pix = st.text_input("Chave PIX", value=dados_colab.get('chave_pix', ''))
            
            if st.button("Gerar Ordem de Pagamento"):
                if not pix.strip() or vlr_tot <= 0:
                    st.error("PIX obrigatório e valor deve ser maior que zero.")
                else:
                    desc = f"{tipo_pagamento} - {dados_colab['nome_completo']} | Centro de Custo: {dados_colab['setor']} | Cargo: {dados_colab['cargo']} | PIX: {pix}" + (f" | {qtd}x R${vlr_un:.2f}" if tipo_pagamento == "Diária" else "")
                    cat = "Diárias Operacionais" if tipo_pagamento == "Diária" else "Adiantamento Salarial"
                    supabase.table("lancamentos_financeiros").insert({
                        "descricao": desc, "categoria": cat, "valor": vlr_tot, 
                        "data_vencimento": dt_pag.strftime("%Y-%m-%d"), "status_lancamento": "Aprovação Pendente Financeiro"
                    }).execute()
                    st.success("Ordem enviada para o Financeiro.")

    elif menu_operacoes == "❌ Registro de Faltas":
        st.subheader("Apontamento de Faltas")
        aptos = supabase.table("colaboradores").select("id, nome_completo, cargo").eq("status_fluxo", "Operação Liberada").execute().data
        if aptos:
            opcoes_colab = {f"{c['nome_completo']} ({c['cargo']})": c for c in aptos}
            dados_falta = opcoes_colab[st.selectbox("Colaborador Ausente:", list(opcoes_colab.keys()))]
            dt_falta = st.date_input("Data da Falta")
            motivo = st.text_area("Observação")
            if st.button("Registrar Falta"):
                try:
                    supabase.table("registro_faltas").insert({
                        "id_colaborador": dados_falta['id'], "nome_colaborador": dados_falta['nome_completo'],
                        "data_falta": dt_falta.strftime("%Y-%m-%d"), "observacao": motivo, "status_falta": "Pendente"
                    }).execute()
                    st.success("Falta registrada e enviada para consolidação do Financeiro.")
                except:
                    st.warning("⚠️ Rode o comando SQL no Supabase para atualizar a tabela 'registro_faltas' com a coluna de status!")
                    
    elif menu_operacoes == "🚪 Desligamento (Demissão)":
        st.subheader("Desligamento de Colaborador Ativo")
        st.caption("Esta ação move o colaborador para a fila de Acerto do RH.")
        
        aptos = supabase.table("colaboradores").select("*").eq("status_fluxo", "Operação Liberada").execute().data
        if not aptos:
            st.warning("Nenhum colaborador ativo no momento para desligamento.")
        else:
            opcoes_colab = {f"{c['nome_completo']} ({c['cargo']})": c for c in aptos}
            dados_demissao = opcoes_colab[st.selectbox("Selecione o Colaborador a ser desligado:", list(opcoes_colab.keys()))]
            
            motivo_demissao = st.text_area("Descreva o motivo do desligamento / Quebra de Contrato:")
            aviso_arq = st.file_uploader("Anexar Aviso/Carta de Demissão (Opcional - Imagem/PDF)", type=["pdf", "png", "jpg", "jpeg"])
            
            if st.button("Confirmar Desligamento da Empresa"):
                if not motivo_demissao.strip():
                    st.error("⚠️ A descrição do motivo é obrigatória.")
                else:
                    url_aviso = ""
                    if aviso_arq:
                        nome_colab_limpo = limpar_nome_arquivo(dados_demissao['nome_completo'])
                        cpf_limpo = str(dados_demissao.get('cpf', '')).replace('.', '').replace('-', '')
                        pasta_funcionario = f"{nome_colab_limpo}_{cpf_limpo}"
                        
                        ext = "pdf" if "pdf" in aviso_arq.name.lower() else "jpg"
                        nome_aviso = f"{pasta_funcionario}/Demissao/Aviso_Desligamento.{ext}"
                        try:
                            supabase.storage.from_(BUCKET_STORAGE).upload(nome_aviso, aviso_arq.getvalue(), {"upsert": "true"})
                            url_aviso = supabase.storage.from_(BUCKET_STORAGE).get_public_url(nome_aviso)
                        except:
                            url_aviso = ""
                            
                    try:
                        supabase.table("colaboradores").update({
                            "status_fluxo": "Desligamento da empresa",
                            "motivo_desligamento": motivo_demissao,
                            "url_aviso_desligamento": url_aviso
                        }).eq("id", dados_demissao['id']).execute()
                        st.success(f"✅ {dados_demissao['nome_completo']} desligado com sucesso. Informações enviadas para o RH.")
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}.")

    elif menu_operacoes == "📊 Produção Diária":
        st.subheader("📊 Cadastro de Produção Diária de Campo")
        st.caption("Registe o volume abatido (exploração) e romaneado (pátio) no dia (com precisão de 3 casas decimais).")
        
        with st.form("form_producao_diaria"):
            dt_prod = st.date_input("Data da Produção", value=datetime.now())
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.write("**🌲 Abate (Exploração Florestal)**")
                arv_abat = st.number_input("Árvores Abatidas (Qtd)", min_value=0, value=0, step=1)
                vol_abat = st.number_input("Volume Abatido (m³)", min_value=0.0, value=0.000, step=0.001, format="%.3f")
            with col_p2:
                st.write("**🪵 Romaneio (Pátio / Serraria)**")
                arv_rom = st.number_input("Árvores Romaneadas (Qtd)", min_value=0, value=0, step=1)
                vol_rom = st.number_input("Volume Romaneado (m³)", min_value=0.0, value=0.000, step=0.001, format="%.3f")
                
            if st.form_submit_button("💾 Salvar Produção Diária"):
                try:
                    supabase.table("producao_diaria").insert({
                        "data_producao": dt_prod.strftime("%Y-%m-%d"),
                        "arvores_abatidas": int(arv_abat),
                        "volume_abatido_m3": float(vol_abat),
                        "arvores_romaneadas": int(arv_rom),
                        "volume_romaneado_m3": float(vol_rom)
                    }).execute()
                    st.success("✅ Produção diária registada com sucesso na base de dados!")
                except Exception as e:
                    st.error(f"⚠️ Erro ao salvar. Detalhes: {e}")

    elif menu_operacoes == "👥 Colaboradores em Operação":
        renderizar_painel_colaboradores_ativos()

# ---------------------------------------------------------
# 3. LANÇAMENTOS FINANCEIROS E RECIBOS (JONAS)
# ---------------------------------------------------------
elif perfil_usuario == "Lançamentos Financeiros (Jonas)":
    st.header("📄 Gestão Financeira e Contabilidade")
    
    pagos_notificacao = supabase.table("lancamentos_financeiros").select("id").eq("status_lancamento", "Pago & Concluído").execute().data
    if pagos_notificacao and len(pagos_notificacao) > 0:
        st.warning(f"🔔 **NOVO EVENTO DE PAGAMENTO:** Matheus acabou de executar {len(pagos_notificacao)} pagamento(s)! Vá na aba '📂 Concluídos' para arquivar.")
    
    aba1, aba2, aba3, aba4, aba_folha_j, aba_ativos_j = st.tabs(["🔔 Aprovações", "📝 Novo Lançamento Manual", "📂 Concluídos e Recibos", "📊 Fechamento Mensal", "💵 Gestão da Folha", "👥 Colaboradores em Operação"])
    
    with aba1:
        ordens = supabase.table("lancamentos_financeiros").select("*").eq("status_lancamento", "Aprovação Pendente Financeiro").execute().data
        if not ordens:
            st.info("Nenhuma solicitação pendente da operação.")
        else:
            for ordem in ordens:
                with st.expander(f"Aprovar: R$ {ordem['valor']:.2f} - {ordem['descricao'][:40]}..."):
                    st.write(f"**Detalhes:** {ordem['descricao']}")
                    if st.button("Aprovar e Enviar p/ Pagamento", key=f"apr_{ordem['id']}"):
                        supabase.table("lancamentos_financeiros").update({"status_lancamento": "Lançado - Aguardando Pagamento"}).eq("id", ordem['id']).execute()
                        st.success("Aprovado!"); st.rerun()

    with aba2:
        st.write("Preencha os dados da despesa esporádica / avulsa:")
        with st.form("form_fin"):
            desc_principal = st.text_input("Fornecedor / Título Curto (Ex: Posto de Gasolina Silva)")
            desc_evento = st.text_area("Descrição do Evento / Motivo da Compra de Madeira / Manutenção:")
            chave_pix_favorecido = st.text_input("Chave PIX do Favorecido")
            cat = st.selectbox("Categoria", ["Peças e Manutenção", "Combustível", "Serviços/Contratos", "Impostos/Taxas", "Madeira", "Outros"])
            vlr = st.number_input("Valor (R$)", min_value=0.01)
            venc = st.date_input("Vencimento")
            
            if st.form_submit_button("Lançar para Pagamento (Enviar p/ Matheus)"):
                if not desc_principal.strip() or not chave_pix_favorecido.strip():
                    st.error("O Título do fornecedor e a Chave PIX são obrigatórios!")
                else:
                    descricao_completa = f"{desc_principal} | Evento: {desc_evento} | PIX: {chave_pix_favorecido}"
                    supabase.table("lancamentos_financeiros").insert({
                        "descricao": descricao_completa, "categoria": cat, "valor": vlr, 
                        "data_vencimento": venc.strftime("%Y-%m-%d"), "status_lancamento": "Lançado - Aguardando Pagamento"
                    }).execute()
                    st.success("Lançamento registrado e enviado para a fila de pagamento do Matheus.")

    with aba3:
        st.subheader("Histórico Recente de Pagamentos")
        st.caption("Baixe o PDF e clique em Arquivar para remover a ordem desta tela.")
        pagos = supabase.table("lancamentos_financeiros").select("*").eq("status_lancamento", "Pago & Concluído").order("id", desc=True).limit(50).execute().data
        
        if not pagos:
            st.info("Sua tela está limpa! Nenhum pagamento aguardando baixa contábil.")
        else:
            for p in pagos:
                with st.expander(f"✅ R$ {p['valor']:.2f} - {p['descricao'][:30]}..."):
                    st.write(f"**Detalhes completos:** {p['descricao']}")
                    st.write(f"**Banco Utilizado:** {p.get('url_comprovante_pago', 'N/A')}")
                    pdf_recibo = gerar_pdf_ordem_pagamento(p)
                    st.download_button(label="📄 Baixar Recibo de Pagamento (PDF)", data=pdf_recibo, file_name=f"Recibo_Pagamento_{p['id']}.pdf", mime="application/pdf", key=f"dl_recibo_{p['id']}")
                    
                    if st.button("📥 Confirmar Baixa e Arquivar no Supabase", key=f"arq_{p['id']}"):
                        nome_arquivo_recibo = f"Recibo_{p['id']}.pdf"
                        url_pdf_recibo = ""
                        try:
                            supabase.storage.from_(BUCKET_STORAGE).upload(nome_arquivo_recibo, pdf_recibo, {"content-type": "application/pdf", "upsert": "true"})
                            url_pdf_recibo = supabase.storage.from_(BUCKET_STORAGE).get_public_url(nome_arquivo_recibo)
                        except Exception:
                            url_pdf_recibo = ""
                        
                        banco_salvo = p.get('url_comprovante_pago') or 'N/A'
                        supabase.table("lancamentos_financeiros").update({
                            "status_lancamento": "Arquivado",
                            "url_comprovante_pago": f"{banco_salvo} | Backup: {url_pdf_recibo}"
                        }).eq("id", p['id']).execute()
                        st.success("Recibo arquivado com sucesso!"); st.rerun()

    with aba4:
        st.subheader("Consolidação para Contabilidade (Dia 01)")
        st.caption("Gere o relatório agrupado de todas as Faltas e Adiantamentos pendentes no mês.")
        try:
            faltas_mes = supabase.table("registro_faltas").select("*").eq("status_falta", "Pendente").execute().data
        except:
            faltas_mes = []
            
        adiant_mes = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Adiantamento Salarial").eq("status_lancamento", "Arquivado").execute().data
        
        st.write(f"📌 **Faltas acumuladas:** {len(faltas_mes)}")
        st.write(f"💸 **Adiantamentos (já pagos) a consolidar:** {len(adiant_mes)}")
        
        if st.button("Gerar PDF de Fechamento e Enviar"):
            if not faltas_mes and not adiant_mes:
                st.info("Não existem Faltas nem Adiantamentos pendentes para consolidar neste momento.")
            else:
                mes_atual_formatado = datetime.now().strftime("%B / %Y").upper()
                pdf_fechamento_bytes = gerar_pdf_fechamento_mensal(mes_atual_formatado, faltas_mes, adiant_mes)
                nome_arq = f"Fechamento_Contabil_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                try:
                    supabase.storage.from_(BUCKET_STORAGE).upload(nome_arq, pdf_fechamento_bytes, {"content-type": "application/pdf"})
                except Exception:
                    pass
                for f in faltas_mes:
                    supabase.table("registro_faltas").update({"status_falta": "Enviado Contabilidade"}).eq("id", f['id']).execute()
                for a in adiant_mes:
                    supabase.table("lancamentos_financeiros").update({"status_lancamento": "Enviado Contabilidade"}).eq("id", a['id']).execute()
                
                st.success("✅ Fechamento processado e arquivado no Supabase com sucesso!")
                st.download_button(label="📄 Baixar Relatório Consolidado (PDF)", data=pdf_fechamento_bytes, file_name=nome_arq, mime="application/pdf")

    with aba_folha_j:
        st.subheader("Aprovação e Quitação da Folha de Pagamento")
        folhas_pendentes_j = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Folha de Pagamento").eq("status_lancamento", "Aprovação Pendente Folha").execute().data
        
        if not folhas_pendentes_j:
            st.info("Nenhuma folha de pagamento aguardando aprovação no momento.")
        else:
            for f_pend in folhas_pendentes_j:
                with st.expander(f"💵 Folha: R$ {f_pend['valor']:.2f} - {f_pend['descricao'][:40]}"):
                    st.write(f"**Detalhes:** {f_pend['descricao']}")
                    if st.button("Aprovar Folha e Enviar p/ Matheus Pagar", key=f"apr_folha_{f_pend['id']}"):
                        supabase.table("lancamentos_financeiros").update({"status_lancamento": "Folha - Aguardando Pagamento"}).eq("id", f_pend['id']).execute()
                        st.success("Folha aprovada e enviada para o Matheus!")
                        st.rerun()

        st.divider()
        st.subheader("Quitação de Folhas Pagas pelo Matheus")
        folhas_pagas_j = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Folha de Pagamento").eq("status_lancamento", "Pago & Concluído").execute().data
        
        if not folhas_pagas_j:
            st.info("Nenhuma folha paga aguardando quitação.")
        else:
            for f_paga in folhas_pagas_j:
                with st.expander(f"✅ Pago: R$ {f_paga['valor']:.2f} - {f_paga['descricao'][:30]}"):
                    st.write(f"**Detalhes:** {f_paga['descricao']}")
                    st.write(f"**Banco Utilizado:** {f_paga.get('url_comprovante_pago', 'N/A')}")
                    
                    if st.button("Dar Quitação Definitiva no Sistema Financeiro", key=f"quit_folha_{f_paga['id']}"):
                        supabase.table("lancamentos_financeiros").update({"status_lancamento": "Arquivado"}).eq("id", f_paga['id']).execute()
                        st.success("Quitação dada com sucesso! Lançamento arquivado.")
                        st.rerun()

    with aba_ativos_j:
        renderizar_painel_colaboradores_ativos()

# ---------------------------------------------------------
# 4. EXECUÇÃO DE PAGAMENTOS (MATHEUS)
# ---------------------------------------------------------
elif perfil_usuario == "Execução de Pagamentos (Matheus)":
    st.header("💳 Execução de Pagamentos")
    
    aba_geral_m, aba_folha_m, aba_ativos_m = st.tabs(["📌 Despesas Gerais", "💵 Folha de Pagamento", "👥 Colaboradores em Operação"])
    
    with aba_geral_m:
        contas = supabase.table("lancamentos_financeiros").select("*").eq("status_lancamento", "Lançado - Aguardando Pagamento").execute().data
        if not contas:
            st.info("Nenhum pagamento pendente no momento.")
        else:
            for conta in contas:
                with st.expander(f"💰 R$ {conta['valor']:.2f} - {conta['descricao'][:35]}..."):
                    st.write(f"**Detalhes da Cobrança:** {conta['descricao']}")
                    
                    chave_pix_extraida = ""
                    nome_favorecido = "Fornecedor / Colaborador"
                    if "PIX: " in conta['descricao']:
                        try:
                            chave_pix_extraida = conta['descricao'].split("PIX: ")[1].split(" |")[0].strip()
                        except:
                            pass
                    if "-" in conta['descricao'] and "|" in conta['descricao']:
                        try:
                            nome_favorecido = conta['descricao'].split("-")[1].split("|")[0].strip()
                        except:
                            pass
                    
                    if chave_pix_extraida:
                        st.divider()
                        st.write("📱 **Área de Pagamento PIX**")
                        payload_pix = formata_pix(chave_pix_extraida, conta['valor'], nome_favorecido)
                        col_qr, col_info = st.columns([1, 2])
                        with col_qr:
                            url_qr = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={payload_pix}"
                            st.image(url_qr, caption="Aponte a Câmera")
                        with col_info:
                            st.info(f"**Chave PIX Original:** {chave_pix_extraida}")
                            st.write("📄 **PIX Copia e Cola:**")
                            st.code(payload_pix, language="text")
                    
                    st.divider()
                    banco_selecionado = st.selectbox("Conta / Banco de Saída:", ["BB_Cupixi", "BB_FA", "Bradesco_FA", "Outra"], key=f"banco_{conta['id']}")
                    banco_final = banco_selecionado
                    if banco_selecionado == "Outra":
                        banco_final = st.text_input("Descreva o Banco de Saída:", key=f"banco_outra_{conta['id']}")
                    
                    if st.button("Confirmar Pagamento Realizado", key=f"btn_pago_{conta['id']}"):
                        if banco_selecionado == "Outra" and not banco_final.strip():
                            st.error("⚠ Por favor, digite o nome do banco utilizado.")
                        else:
                            supabase.table("lancamentos_financeiros").update({
                                "status_lancamento": "Pago & Concluído",
                                "url_comprovante_pago": banco_final
                            }).eq("id", conta['id']).execute()
                            st.success("Pagamento confirmado!"); st.rerun()

    with aba_folha_m:
        st.subheader("Pagamento de Folhas Aprovadas")
        folhas_matheus = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Folha de Pagamento").eq("status_lancamento", "Folha - Aguardando Pagamento").execute().data
        
        if not folhas_matheus:
            st.info("Nenhuma folha de pagamento pendente para execução.")
        else:
            for f_mat in folhas_matheus:
                with st.expander(f"💵 Folha: R$ {f_mat['valor']:.2f} - {f_mat['descricao'][:35]}"):
                    st.write(f"**Detalhes:** {f_mat['descricao']}")
                    
                    chave_pix_f = ""
                    if "PIX: " in f_mat['descricao']:
                        try:
                            chave_pix_f = f_mat['descricao'].split("PIX: ")[1].split(" |")[0].strip()
                        except:
                            pass
                            
                    if chave_pix_f:
                        st.divider()
                        st.write("📱 **PIX da Folha**")
                        payload_f = formata_pix(chave_pix_f, f_mat['valor'], "Colaborador")
                        st.code(payload_f, language="text")
                        
                    st.divider()
                    banco_f = st.selectbox("Banco de Saída:", ["BB_Cupixi", "BB_FA", "Bradesco_FA", "Outra"], key=f"banco_f_{f_mat['id']}")
                    banco_f_final = banco_f
                    if banco_f == "Outra":
                        banco_f_final = st.text_input("Descreva o Banco:", key=f"banco_f_out_{f_mat['id']}")
                        
                    if st.button("Confirmar Pagamento da Folha", key=f"btn_pago_folha_{f_mat['id']}"):
                        supabase.table("lancamentos_financeiros").update({
                            "status_lancamento": "Pago & Concluído",
                            "url_comprovante_pago": banco_f_final
                        }).eq("id", f_mat['id']).execute()
                        st.success("Pagamento da folha confirmado! O evento voltou para a tela do Jonas.")
                        st.rerun()

    with aba_ativos_m:
        renderizar_painel_colaboradores_ativos()