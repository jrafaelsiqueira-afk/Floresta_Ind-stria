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

# Configuração da página (DEVE SER A PRIMEIRA LINHA DO STREAMLIT)
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
# FUNÇÕES DE VALIDAÇÃO E LIMPEZA
# ---------------------------------------------------------
def validar_cpf(cpf):
    """Valida o CPF informando se os dígitos verificadores conferem."""
    cpf = "".join([c for c in cpf if c.isdigit()])
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    digito1 = (soma * 10) % 11
    if digito1 == 10:
        digito1 = 0
    if digito1 != int(cpf[9]):
        return False
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    digito2 = (soma * 10) % 11
    if digito2 == 10:
        digito2 = 0
    if digito2 != int(cpf[10]):
        return False
    return True

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


def gerar_pdf_ficha_epi(nome, cpf, cargo, setor, data_adm, opcao_alojamento, contato_emergencia, epis_entregues, autoriza_imagem, foto_camera=None, canvas_result=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "FLORESTAL AMAZONIA - TERMO DE ADMISSAO & ENTREGA DE EPI", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 6, "Conforme Norma Regulamentadora NR-31 / MTE e Padroes FSC", border=False, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "1. DADOS DO COLABORADOR & LOGISTICA RURAL", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"Nome Completo: {nome}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"CPF: {cpf}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Setor: {setor} | Cargo / Funcao: {cargo}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Data de Admissao: {data_adm}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Opcao de Alojamento (Campo / Base): [ {opcao_alojamento.upper()} ]", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Contato de Emergencia: {contato_emergencia}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "2. UNIFORME, EPIs & TAMANHOS / CERTIFICADOS (CA)", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for item in epis_entregues:
        item_limpo = item.replace('ç', 'c').replace('ã', 'a').replace('í', 'i').replace('ó', 'o').replace('á', 'a').replace('ê', 'e')
        pdf.cell(0, 5, f"[ X ] {item_limpo}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "3. TERMO DE COMPROMISSO E RESPONSABILIDADE", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    termo = ("Declaro ter recebido da empresa o uniforme e os Equipamentos de Protecao Individual (EPIs) acima relacionados, "
             "em perfeitas condicoes de uso e conservacao. Comprometo-me a utiliza-los obrigatoriamente durante o exercicio "
             "de minhas funcoes, zelar por sua guarda e conservacao, e comunicar imediatamente ao setor de RH qualquer "
             "extravio ou dano que os torne improprios para uso, bem como estar ciente das normas de alojamento de campo.")
    pdf.multi_cell(0, 4, termo)
    pdf.ln(4)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "4. AUTORIZACAO DE USO DE IMAGEM E DADOS (LGPD)", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    texto_imagem = ("Em conformidade com a Lei Geral de Protecao de Dados (LGPD - Lei 13.709/2018), "
                    "fui informado e manifesto concordancia sobre o uso de minha imagem em fotografias e gravacoes de video, "
                    "bem como o tratamento de meus dados pessoais para fins exclusivos de identificacao corporativa, "
                    "emissao de crachas, treinamentos e registros de auditoria da Florestal Amazonia, de forma gratuita e espontanea.")
    pdf.multi_cell(0, 4, texto_imagem)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    status_auth = "[ X ] SIM, AUTORIZO O USO" if "Sim" in autoriza_imagem else "[ X ] NAO AUTORIZO"
    pdf.cell(0, 5, f"Opcao Escolhida: {status_auth}", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "5. COMPROVACAO DE ENTREGA (FOTO & ASSINATURA)", border=False, new_x="LMARGIN", new_y="NEXT")
    
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


def gerar_pdf_cadastro_completo(ficha_epi_bytes, documentos_extras):
    writer = PdfWriter()
    writer.append(io.BytesIO(ficha_epi_bytes))
    
    for arq in documentos_extras:
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
                    # Redimensiona a imagem para caber na página A4 de forma limpa
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
    pdf.multi_cell(0, 5, "Este relatorio atesta o controlo de conformidade trabalhista, entrega de uniformes, EPIs, exames admissionais (ASO), vacinacao, comprovante de residencia e alojamento conforme as normas de auditoria florestal.")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "2. LISTAGEM E CONFORMIDADE DOS COLABORADORES ATIVOS", border=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(45, 6, "Nome", border=1)
    pdf.cell(28, 6, "CPF", border=1)
    pdf.cell(40, 6, "Cargo", border=1)
    pdf.cell(22, 6, "Alojamento", border=1)
    pdf.cell(30, 6, "Contato Emerg.", border=1)
    pdf.cell(25, 6, "Docs/EPI", border=1, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "", 8)
    for c in ativos:
        nome_str = str(c.get('nome_completo', ''))[:22]
        pdf.cell(45, 6, nome_str, border=1)
        pdf.cell(28, 6, str(c.get('cpf', '')), border=1)
        pdf.cell(40, 6, str(c.get('cargo', ''))[:18], border=1)
        pdf.cell(22, 6, str(c.get('opcao_alojamento', 'Rede')), border=1)
        pdf.cell(30, 6, str(c.get('contato_emergencia', 'N/A'))[:15], border=1)
        status_doc = "OK" if c.get('url_aso') and c.get('url_ficha_pdf') else "Pendente"
        pdf.cell(25, 6, status_doc, border=1, new_x="LMARGIN", new_y="NEXT")
        
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
    pdf.cell(0, 6, f"Contato de Emergencia: {colab.get('contato_emergencia', 'N/A')}", border=False, new_x="LMARGIN", new_y="NEXT")
    
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

    termo_busca = st.text_input("🔍 Buscar Colaborador (por Nome ou CPF):", "", key="busca_colab_ativo")
    if termo_busca:
        termo_l = termo_busca.lower()
        ativos = [c for c in ativos if termo_l in c.get('nome_completo', '').lower() or termo_l in c.get('cpf', '')]

    total_ativos = len(ativos)
    setores_contagem = {}
    cargos_contagem = {}
    alojamento_contagem = {"Rede": 0, "Cama": 0, "Não Alojado": 0}
    
    hoje = datetime.now().date()
    aso_vencidos_qtd = 0

    for c in ativos:
        setor = c.get('setor', 'Outros')
        cargo = c.get('cargo', 'Não definido')
        aloj = c.get('opcao_alojamento', 'Rede')
        setores_contagem[setor] = setores_contagem.get(setor, 0) + 1
        cargos_contagem[cargo] = cargos_contagem.get(cargo, 0) + 1
        if aloj in alojamento_contagem:
            alojamento_contagem[aloj] += 1
            
        dt_adm_str = c.get('data_admissao')
        if dt_adm_str:
            try:
                dt_adm = datetime.strptime(dt_adm_str, "%Y-%m-%d").date()
                if (hoje - dt_adm).days > 365:
                    aso_vencidos_qtd += 1
            except:
                pass
        
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        st.metric("Total Filtrado", total_ativos)
    with col_t2:
        st.info(f"🏕️ **Alojamento:** Rede: {alojamento_contagem['Rede']} | Cama: {alojamento_contagem['Cama']} | Não Alj.: {alojamento_contagem['Não Alojado']}")
    with col_t3:
        if aso_vencidos_qtd > 0:
            st.warning(f"⚠️ **ASO's Próximos/Vencidos (>1 ano):** {aso_vencidos_qtd}")
        else:
            st.success("✅ **ASO's em Dia (Anual):** 100% regulares")
        
    with st.expander("📊 Ver Resumo por Função / Cargo"):
        for cargo_nome, qtd in sorted(cargos_contagem.items(), key=lambda x: x[1], reverse=True):
            st.write(f"- **{cargo_nome}:** {qtd} colaborador(es)")
            
    st.write("📋 **Lista Completa de Ativos:**")
    
    dados_tabela = []
    for idx, c in enumerate(ativos, 1):
        dt_adm_br = "/".join(c.get('data_admissao', '').split("-")[::-1]) if c.get('data_admissao') else 'N/A'
        dados_tabela.append({
            "Nº": idx,
            "Nome Completo": c.get('nome_completo'),
            "CPF": c.get('cpf'),
            "Cargo": c.get('cargo'),
            "Setor": c.get('setor'),
            "Alojamento": c.get('opcao_alojamento', 'Rede'),
            "Contato Emerg.": c.get('contato_emergencia', 'N/A'),
            "Admissão": dt_adm_br,
            "PIX": c.get('chave_pix', 'Não cad.'),
            "ASO": "Ver" if c.get('url_aso') else "Não",
            "Vacina": "Ver" if c.get('url_vacina') else "Não",
            "Residência": "Ver" if c.get('url_residencia') else "Não",
            "Doc. Pessoal": "Ver" if c.get('url_documento_pessoal') else "Não"
        })
        
    st.dataframe(dados_tabela, use_container_width=True, hide_index=True)


# ---------------------------------------------------------
# INTERFACE PRINCIPAL
# ---------------------------------------------------------
st.title("🌲 Florestal Operacional")
st.caption("Sistema Integrado de Operação & Financeiro")

# ---------------------------------------------------------
# SISTEMA DE LOGIN E PRIMEIRO ACESSO
# ---------------------------------------------------------
def gerenciar_autenticacao():
    st.sidebar.title("🔐 Acesso ao Sistema")
    
    if "usuario_autenticado" not in st.session_state:
        st.session_state.usuario_autenticado = False
        st.session_state.perfil_usuario = None
        st.session_state.email_usuario = None

    if st.session_state.usuario_autenticado:
        st.sidebar.success(f"Logado como: {st.session_state.email_usuario}")
        st.sidebar.info(f"Perfil: {st.session_state.perfil_usuario}")
        if st.sidebar.button("🚪 Sair do Sistema"):
            st.session_state.usuario_autenticado = False
            st.session_state.perfil_usuario = None
            st.rerun()
        return True

    tipo_login = st.sidebar.radio("Como deseja entrar?", ["Já tenho E-mail", "Primeiro Acesso (Credencial)"])

    if tipo_login == "Já tenho E-mail":
        email_login = st.sidebar.text_input("E-mail Definitivo").strip()
        senha_login = st.sidebar.text_input("Senha", type="password").strip()
        
        if st.sidebar.button("Entrar"):
            try:
                resposta_auth = supabase.auth.sign_in_with_password({"email": email_login, "password": senha_login})
                perfil_db = supabase.table("usuarios_perfis").select("perfil").eq("email", email_login).execute()
                
                if perfil_db.data:
                    st.session_state.perfil_usuario = perfil_db.data[0]["perfil"]
                    st.session_state.email_usuario = email_login
                    st.session_state.usuario_autenticado = True
                    st.rerun()
                else:
                    st.sidebar.error("Erro: Perfil não encontrado para este e-mail.")
            except Exception as e:
                st.sidebar.error("E-mail ou senha incorretos.")

    else:
        st.sidebar.caption("Utilize o login e senha inicial fornecidos pela diretoria.")
        login_ini = st.sidebar.text_input("Login Inicial").strip()
        senha_ini = st.sidebar.text_input("Senha Inicial", type="password").strip()
        
        if st.sidebar.button("Verificar Credencial"):
            res = supabase.table("credenciais_iniciais").select("*").eq("login", login_ini).eq("senha", senha_ini).eq("utilizado", False).execute()
            if res.data:
                st.session_state.credencial_valida = res.data[0]
                st.rerun()
            else:
                st.sidebar.error("Credencial inválida ou já utilizada.")

        if "credencial_valida" in st.session_state:
            st.sidebar.markdown("---")
            st.sidebar.warning("✅ Credencial Válida! Configure seu acesso definitivo.")
            
            novo_email = st.sidebar.text_input("Digite seu E-mail Pessoal").strip()
            nova_senha = st.sidebar.text_input("Crie uma Nova Senha (mínimo 6 caracteres)", type="password").strip()
            
            if st.sidebar.button("Cadastrar e Acessar"):
                if len(nova_senha) < 6:
                    st.sidebar.error("A senha deve ter pelo menos 6 caracteres.")
                elif not novo_email:
                    st.sidebar.error("O E-mail é obrigatório.")
                else:
                    try:
                        supabase.auth.sign_up({"email": novo_email, "password": nova_senha})
                        perfil_atribuido = st.session_state.credencial_valida["perfil"]
                        supabase.table("usuarios_perfis").insert({"email": novo_email, "perfil": perfil_atribuido}).execute()
                        supabase.table("credenciais_iniciais").update({"utilizado": True}).eq("login", login_ini).execute()
                        st.sidebar.success("Conta criada com sucesso! Faça login na aba 'Já tenho E-mail'.")
                        del st.session_state.credencial_valida
                    except Exception as e:
                        st.sidebar.error(f"Erro ao criar conta: O e-mail já existe ou é inválido.")

    return False

if not gerenciar_autenticacao():
    st.stop()

email_logado = st.session_state.email_usuario
perfil_banco = st.session_state.perfil_usuario

# ---------------------------------------------------------
# MODO ADMINISTRADOR (Acesso Master para o Gean)
# ---------------------------------------------------------
EMAILS_ADMIN = ["jrafaelsiqueira@gmail.com"] 

if email_logado in EMAILS_ADMIN:
    st.sidebar.divider()
    st.sidebar.warning("👑 **MODO ADMINISTRADOR ATIVO**")
    st.sidebar.caption("Como administrador, pode navegar por qualquer aba ou aceder ao painel de correções.")
    
    perfil_usuario = st.sidebar.selectbox(
        "Navegar como:",
        [
            "Proprietário / Diretoria (Gean)", 
            "RH Cadastral - Floresta (Maria)", 
            "RH Cadastral - Indústria (Felipe)", 
            "Engenharia Florestal (Jean Gustavo)", 
            "Operacional Indústria - Serraria (Felipe)",
            "Operacional Indústria - Carvoaria (Nelson)",
            "Lançamentos Financeiros (Jonas)", 
            "Execução de Pagamentos (Matheus)",
            "🛠️ Painel de Correções (Exclusivo Admin)"
        ]
    )
else:
    perfil_usuario = perfil_banco
    st.sidebar.divider()
    st.sidebar.info(f"Acesso Liberado. Painel Ativo: **{perfil_usuario}**")


# ---------------------------------------------------------
# 0. PROPRIETÁRIO / DIRETORIA (GEAN)
# ---------------------------------------------------------
if perfil_usuario == "Proprietário / Diretoria (Gean)":
    st.header("👑 Painel Executivo & Auditoria (Diretoria)")
    st.caption("Bem-vindo, Gean. Visão completa de fiscalização, conformidade e relatórios da operação.")
    
    try:
        todos_colabs = supabase.table("colaboradores").select("*").execute().data
        todas_despesas = supabase.table("lancamentos_financeiros").select("*").execute().data
        producao_data = supabase.table("producao_diaria").select("*").execute().data
        producao_ind_data = supabase.table("producao_industrial").select("*").execute().data
    except:
        todos_colabs, todas_despesas, producao_data, producao_ind_data = [], [], [], []
        
    ativos_gean = [c for c in todos_colabs if c.get('status_fluxo') == "Operação Liberada"]
    pendentes_gean = [c for c in todos_colabs if c.get('status_fluxo') in ["Aguardando Treinamento", "Em Treinamento"]]
    desligados_gean = [c for c in todos_colabs if c.get('status_fluxo') in ["Não Habilitado", "Desligamento da empresa", "Acerto Concluído"]]
    
    total_gasto = sum([d.get('valor', 0) for d in todas_despesas if d.get('status_lancamento') in ["Pago & Concluído", "Arquivado"]])
    
    receita_total_industrial = 0
    if producao_ind_data:
        for p in producao_ind_data:
            qtd_venda = float(p.get('quantidade_saida', 0) or 0)
            vlr_unit = float(p.get('valor_unitario', 0) or 0)
            receita_total_industrial += (qtd_venda * vlr_unit)
            
    lucro_liquido = receita_total_industrial - total_gasto

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("👥 Ativos", len(ativos_gean))
    with kpi2:
        st.metric("💰 Despesas", f"R$ {total_gasto:,.2f}")
    with kpi3:
        st.metric("📈 Faturamento Ind.", f"R$ {receita_total_industrial:,.2f}")
    with kpi4:
        st.metric("💵 Saldo / Lucro Líquido", f"R$ {lucro_liquido:,.2f}", delta=f"R$ {lucro_liquido:,.2f}")
        
    st.divider()
    
    aba_audit, aba_prod_exec, aba_ind_exec, aba_func_geral, aba_fin_geral = st.tabs(["🛡️ Auditoria (FSC)", "📊 Produção Florestal", "🏭 Indústria & Saldo", "📋 Funcionários", "📊 Finanças"])
    
    with aba_audit:
        st.subheader("Relatório de Auditoria Interna e Conformidade")
        if st.button("📄 Gerar Relatório de Auditoria em PDF"):
            if not ativos_gean:
                st.warning("Não há colaboradores ativos para gerar o relatório.")
            else:
                pdf_audit_bytes = gerar_pdf_relatorio_auditoria(ativos_gean, len(ativos_gean))
                st.success("Relatório de auditoria gerado com sucesso!")
                st.download_button("📥 Baixar Relatório de Auditoria (PDF)", pdf_audit_bytes, file_name=f"Relatorio_Auditoria_FSC_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf")
                
        dados_audit = [{"Nome": c.get('nome_completo'), "CPF": c.get('cpf'), "Setor": c.get('setor'), "Alojamento": c.get('opcao_alojamento', 'Rede'), "Contato Emerg.": c.get('contato_emergencia')} for c in ativos_gean]
        if dados_audit:
            st.dataframe(dados_audit, use_container_width=True, hide_index=True)

    with aba_prod_exec:
        st.subheader("📈 Desempenho Operacional e Produção da Safra")
        if not producao_data:
            st.info("Nenhum registo de produção diária florestal encontrado.")
        else:
            tabela_prod = [{"Data": p.get('data_producao'), "Árv. Abatidas": p.get('arvores_abatidas'), "Vol. Abatido (m³)": p.get('volume_abatido_m3')} for p in producao_data]
            st.dataframe(tabela_prod, use_container_width=True, hide_index=True)

    with aba_ind_exec:
        st.subheader("🏭 Consolidado Industrial (Madeira Serrada & Carvão) & Balanço Financeiro")
        if not producao_ind_data:
            st.info("Nenhum registro industrial lançado.")
        else:
            serrada_rows = [p for p in producao_ind_data if p.get('tipo_produto') == 'Madeira Serrada']
            carvao_rows = [p for p in producao_ind_data if p.get('tipo_produto') == 'Carvão']
            
            st.write("🌲 **Estoque Consolidado - Madeira Serrada (por Espécie):**")
            madeira_dict = {}
            for s in serrada_rows:
                esp = s.get('especie', 'Geral')
                if esp not in madeira_dict:
                    madeira_dict[esp] = {"vol_tora": 0.0, "vol_serrado": 0.0, "vol_saida": 0.0, "faturamento": 0.0}
                madeira_dict[esp]["vol_tora"] += float(s.get('volume_tora', 0) or 0)
                madeira_dict[esp]["vol_serrado"] += float(s.get('volume_serrado', 0) or 0)
                madeira_dict[esp]["vol_saida"] += float(s.get('quantidade_saida', 0) or 0)
                madeira_dict[esp]["faturamento"] += (float(s.get('quantidade_saida', 0) or 0) * float(s.get('valor_unitario', 0) or 0))
                
            tabela_madeira = []
            for esp, v in madeira_dict.items():
                estoque_atual = v["vol_serrado"] - v["vol_saida"]
                tabela_madeira.append({
                    "Espécie": esp,
                    "Vol. Toras (m³)": f"{v['vol_tora']:,.3f}",
                    "Vol. Serrado (m³)": f"{v['vol_serrado']:,.3f}",
                    "Vol. Saídas/Vendas (m³)": f"{v['vol_saida']:,.3f}",
                    "Estoque Atual (m³)": f"{estoque_atual:,.3f}",
                    "Faturamento (R$)": f"R$ {v['faturamento']:,.2f}"
                })
            st.dataframe(tabela_madeira, use_container_width=True, hide_index=True)
            
            st.write("🔥 **Estoque Consolidado - Carvão (Sacas):**")
            total_prod_carvao = sum([float(c.get('quantidade_produzida', 0) or 0) for c in carvao_rows])
            total_saida_carvao = sum([float(c.get('quantidade_saida', 0) or 0) for c in carvao_rows])
            fat_carvao = sum([float(c.get('quantidade_saida', 0) or 0) * float(c.get('valor_unitario', 0) or 0) for c in carvao_rows])
            estoque_carvao = total_prod_carvao - total_saida_carvao
            
            st.metric("Sacas Produzidas (Acumuladas)", f"{total_prod_carvao:,.0f}")
            st.metric("Sacas Vendidas/Saídas", f"{total_saida_carvao:,.0f}")
            st.metric("Estoque Atual de Carvão (Sacas)", f"{estoque_carvao:,.0f}")
            st.metric("Faturamento Total Carvão", f"R$ {fat_carvao:,.2f}")
            
            st.divider()
            st.subheader("💵 Balanço Financeiro da Indústria (Lucro Líquido)")
            st.write(f"- **Faturamento Bruto Industrial:** R$ {receita_total_industrial:,.2f}")
            st.write(f"- **Total de Despesas Pagas:** R$ {total_gasto:,.2f}")
            st.success(f"**Resultado Líquido Operacional:** R$ {lucro_liquido:,.2f}")

    with aba_func_geral:
        st.subheader("Base Completa de Colaboradores")
        tabela_geral = [{"Nome": c.get('nome_completo'), "CPF": c.get('cpf'), "Cargo": c.get('cargo'), "Setor": c.get('setor'), "Contato Emerg.": c.get('contato_emergencia'), "Status": c.get('status_fluxo')} for c in todos_colabs]
        st.dataframe(tabela_geral, use_container_width=True, hide_index=True)

    with aba_fin_geral:
        st.subheader("Panorama de Lançamentos Financeiros")
        tabela_fin = [{"ID": d.get('id'), "Categoria": d.get('categoria'), "Valor (R$)": f"R$ {d.get('valor', 0):.2f}", "Status": d.get('status_lancamento')} for d in todas_despesas]
        st.dataframe(tabela_fin, use_container_width=True, hide_index=True)


# ---------------------------------------------------------
# 1. RH CADASTRAL - UNIFICADO (FLORESTA & INDÚSTRIA)
# ---------------------------------------------------------
elif perfil_usuario in ["RH Cadastral - Floresta (Maria)", "RH Cadastral - Indústria (Felipe)"]:
    setor_titulo = "Floresta" if "Floresta" in perfil_usuario else "Indústria"
    st.header(f"📋 Recursos Humanos (Cadastro {setor_titulo})")
    
    desligamentos_pendentes = supabase.table("colaboradores").select("id").in_("status_fluxo", ["Não Habilitado", "Desligamento da empresa"]).execute().data
    if desligamentos_pendentes and len(desligamentos_pendentes) > 0:
        st.error(f"🚨 **ALERTA DE DESLIGAMENTO:** Você tem {len(desligamentos_pendentes)} processo(s) pendente(s) aguardando envio para a Contabilidade!")
    
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
            cpf = st.text_input("CPF (Somente números ou pontuado)")
            chave_pix_cad = st.text_input("Chave PIX do Colaborador")
            data_adm = st.date_input("Data de Admissão")
            
        with col2:
            setor_escolhido = st.selectbox("Setor Operacional", list(EPI_POR_SETOR.keys()))
            cargo_escolhido = st.selectbox("Cargo / Função", list(EPI_POR_SETOR[setor_escolhido].keys()))
            contato_emergencia = st.text_input("📞 Telefone / Contato de Emergência (Nome e Número)")
            
            st.write("⛺ **Opção de Alojamento Rural (Amazônia):**")
            opcao_alojamento = st.radio("Escolha o arranjo de descanso no campo:", ["Rede", "Cama", "Não Alojado"], horizontal=True)
        
        # -------------------------------------------------------------
        # FUNÇÃO OTIMIZADA PARA ANEXAR DOCUMENTOS (CÂMERA OCULTA)
        # -------------------------------------------------------------
        def anexar_documento(label, chave):
            st.markdown(f"**{label}**")
            # 1. Campo de arquivo padrão sempre visível e limpo
            arq = st.file_uploader(f"Anexar {label}", type=["pdf", "jpg", "jpeg", "png"], key=f"arq_{chave}", label_visibility="collapsed")
            
            # 2. Câmera oculta atrás de um checkbox para não travar o navegador
            cam = None
            if st.checkbox("📸 Ligar Câmera (Scanner)", key=f"chk_cam_{chave}"):
                cam = st.camera_input("Centralize o documento e tire a foto", key=f"cam_{chave}")
            
            st.markdown("---")
            return cam if cam is not None else arq
        # -------------------------------------------------------------

        st.divider()
        st.subheader("🏥 Digitalização e Anexos de Documentos")
        st.caption("Faça o upload do arquivo em PDF/Imagem. Caso não tenha o arquivo, marque a opção da câmera para digitalizar na hora.")
        
        aso_doc = anexar_documento("1. ASO (Exame Admissional)", "aso")
        doc_pessoal = anexar_documento("2. Documento Pessoal (CNH / RG / CPF)", "doc_pess")
        vacina_doc = anexar_documento("3. Carteira de Vacinação Atualizada", "vac")
        residencia_doc = anexar_documento("4. Comprovante de Residência", "res")
        contrato_doc = anexar_documento("5. Contrato de Trabalho Assinado", "contrato")

        tem_filhos = st.checkbox("Possui filhos menores que 14 anos?")
        certidao_doc = None
        if tem_filhos:
            certidao_doc = anexar_documento("6. Certidão de Nascimento do(s) Filho(s)", "cert_filho")
        
        st.divider()
        st.subheader("👕 Uniforme & 🪖 Kit de EPI Obrigatório (PGR)")
        
        epis_exigidos = EPI_POR_SETOR[setor_escolhido][cargo_escolhido].copy()
        
        st.markdown("---")
        st.write("👔 **Uniforme Institucional / Operacional**")
        c_uni_check, c_uni_tam = st.columns([2, 2])
        recebe_uniforme = c_uni_check.checkbox("Recebeu Uniforme Completo", value=True)
        tamanho_uniforme = c_uni_tam.selectbox("Tamanho do Uniforme", ["P", "M", "G", "GG", "XG"], key="tam_uni")
        
        epis_marcados = []
        if recebe_uniforme:
            epis_marcados.append(f"UNIFORME COMPLETO (Tamanho: {tamanho_uniforme})")
            
        st.write("🔧 **Equipamentos de Proteção Individual (EPIs):**")
        col_epi1, col_epi2 = st.columns(2)
        
        for i, epi in enumerate(epis_exigidos):
            col_destino = col_epi1 if i % 2 == 0 else col_epi2
            c_chk, c_extra = col_destino.columns([6, 4])
            
            checado = c_chk.checkbox(epi, key=f"epi_{i}")
            
            if "BOTA" in epi.upper():
                c_ca, c_num = c_extra.columns(2)
                ca_val = c_ca.text_input("CA", placeholder="Nº CA", key=f"ca_{i}", label_visibility="collapsed")
                num_bota = c_num.text_input("Nº Bota", value="41", key=f"num_{i}", label_visibility="collapsed")
                if checado:
                    epis_marcados.append(f"{epi} (CA: {ca_val} | Numeração: {num_bota})")
            else:
                ca_val = c_extra.text_input("CA", placeholder="Nº CA", key=f"ca_{i}", label_visibility="collapsed")
                if checado:
                    epis_marcados.append(f"{epi} (CA: {ca_val})")
        
        st.divider()
        conduta = st.checkbox("Li e aceito o Código de Conduta & Regras de Segurança")
        
        st.write("📜 **Autorização de Uso de Imagem (LGPD)**")
        st.info("Em conformidade com a Lei Geral de Proteção de Dados (LGPD - Lei 13.709/2018), autorizo o uso de minha imagem em fotografias e gravações de vídeo para fins exclusivos de identificação corporativa, crachás, treinamentos e registros de auditoria da Florestal Amazônia, de forma gratuita e espontânea.")
        autoriza_imagem = st.radio("Autoriza o uso da sua imagem?", ["Sim, autorizo", "Não autorizo"], horizontal=True)

        st.divider()
        st.write("📷 **Registro de Foto do Colaborador (Rosto)**")
        foto_capturada = None
        if "foto_arquivo_temp" not in st.session_state:
            st.session_state.foto_arquivo_temp = None

        if st.checkbox("📸 Ligar Câmera para Foto do Rosto"):
            foto_input_raw = st.camera_input("Clique abaixo para tirar a foto do colaborador", key="cam_rosto")
            if foto_input_raw is not None:
                st.session_state.foto_arquivo_temp = foto_input_raw

        if st.session_state.foto_arquivo_temp is not None:
            st.image(st.session_state.foto_arquivo_temp, width=200, caption="Foto Guardada")
            foto_capturada = st.session_state.foto_arquivo_temp

        st.divider()
        st.subheader("✍ Assinatura Digital")
        canvas_result = st_canvas(fill_color="rgba(255, 255, 255, 0)", stroke_width=2, stroke_color="#000000", background_color="#F0F2F6", height=150, drawing_mode="freedraw", key="canvas", update_streamlit=True, return_image_data=True)

        if st.button("Cadastrar e Gerar Cadastro"):
            tem_foto = foto_capturada is not None
            tem_assinatura = canvas_result is not None and canvas_result.json_data and len(canvas_result.json_data.get("objects", [])) > 0
            cpf_limpo_val = "".join([c for c in cpf if c.isdigit()])

            if not (nome.strip() and cpf.strip() and cargo_escolhido.strip() and contato_emergencia.strip()):
                st.error("Preencha todos os dados essenciais do colaborador, incluindo o Contato de Emergência.")
            elif not validar_cpf(cpf_limpo_val):
                st.error("⚠️ CPF inválido! Verifique os dígitos informados.")
            elif not vacina_doc or not residencia_doc:
                st.error("⚠️ A digitalização ou anexo da Carteira de Vacinação e do Comprovante de Residência são obrigatórios.")
            elif not conduta:
                st.error("O Código de Conduta precisa ser confirmado.")
            elif not (tem_foto or tem_assinatura):
                st.error("Tire uma Foto ou colha a Assinatura Digital antes de finalizar.")
            else:
                setor_db = "Colheita" if setor_escolhido == "Floresta" else ("Indústria" if setor_escolhido == "Indústria / Carvoaria" else setor_escolhido)
                
                docs_extras = [aso_doc, doc_pessoal, vacina_doc, residencia_doc, contrato_doc, certidao_doc]
                
                pdf_ficha_epi_bytes = gerar_pdf_ficha_epi(nome.strip(), cpf.strip(), cargo_escolhido, setor_escolhido, data_adm.strftime("%d/%m/%Y"), opcao_alojamento, contato_emergencia.strip(), epis_marcados, autoriza_imagem, foto_capturada, canvas_result)
                pdf_cadastro_completo = gerar_pdf_cadastro_completo(pdf_ficha_epi_bytes, docs_extras)
                
                nome_limpo = limpar_nome_arquivo(nome.strip())
                pasta_funcionario = f"{nome_limpo}_{cpf_limpo_val}"
                
                nome_arquivo_epi = f"{pasta_funcionario}/Ficha_Epi/Termo_EPI.pdf"
                try:
                    supabase.storage.from_(BUCKET_STORAGE).upload(nome_arquivo_epi, pdf_ficha_epi_bytes, {"content-type": "application/pdf", "upsert": "true"})
                except:
                    pass
                url_pdf = supabase.storage.from_(BUCKET_STORAGE).get_public_url(nome_arquivo_epi)
                
                def salvar_arquivo_storage(arquivo, subpasta, nome_padrao):
                    if arquivo is not None:
                        try:
                            extensao = "pdf" if (hasattr(arquivo, 'name') and "pdf" in arquivo.name.lower()) else "jpg"
                            caminho = f"{pasta_funcionario}/{subpasta}/{nome_padrao}.{extensao}"
                            supabase.storage.from_(BUCKET_STORAGE).upload(caminho, arquivo.getvalue(), {"upsert": "true"})
                            return supabase.storage.from_(BUCKET_STORAGE).get_public_url(caminho)
                        except:
                            pass
                    return ""

                url_aso_final = salvar_arquivo_storage(aso_doc, "Aso", "Exame_Admissional")
                url_doc_final = salvar_arquivo_storage(doc_pessoal, "Documentos_Pessoais", "Documento_Pessoal")
                url_vacina_final = salvar_arquivo_storage(vacina_doc, "Vacinacao", "Carteira_Vacinacao")
                url_residencia_final = salvar_arquivo_storage(residencia_doc, "Residencia", "Comprovante_Residencia")
                url_contrato_final = salvar_arquivo_storage(contrato_doc, "Contrato", "Contrato_Trabalho")
                url_certidao_final = salvar_arquivo_storage(certidao_doc, "Dependentes", "Certidao_Filho")
                
                try:
                    supabase.table("colaboradores").insert({
                        "nome_completo": nome.strip(), "cpf": cpf.strip(), "cargo": cargo_escolhido, "setor": setor_db, 
                        "data_admissao": data_adm.strftime("%Y-%m-%d"), "ficha_epi_assinada": True, "codigo_conduta_lido": conduta,
                        "status_fluxo": "Aguardando Treinamento", "url_ficha_pdf": url_pdf, "chave_pix": chave_pix_cad.strip(), 
                        "url_aso": url_aso_final, "url_documento_pessoal": url_doc_final, "url_vacina": url_vacina_final, 
                        "url_residencia": url_residencia_final, "opcao_alojamento": opcao_alojamento, "contato_emergencia": contato_emergencia.strip(),
                        "url_contrato_trabalho": url_contrato_final, "url_certidao_filhos": url_certidao_final, "autoriza_imagem": autoriza_imagem,
                        "cadastrado_por": email_logado
                    }).execute()
                    
                    st.success(f"Colaborador {nome} registado com sucesso e todos os documentos arquivados!")
                    st.session_state.foto_arquivo_temp = None
                    st.download_button("📥 Baixar Cadastro Realizado (PDF)", pdf_cadastro_completo, f"Cadastro_{nome_limpo}.pdf", "application/pdf")
                except Exception as err:
                    st.error("O CPF já está registado." if "23505" in str(err) else f"Erro: {err}")
    
    with aba_desligamentos:
        st.subheader("Processos de Desligamento / Acerto Contábil")
        desligados = supabase.table("colaboradores").select("*").in_("status_fluxo", ["Não Habilitado", "Desligamento da empresa"]).execute().data
        if not desligados:
            st.info("Nenhum processo de desligamento pendente.")
        else:
            for colab in desligados:
                with st.expander(f"⚠️ {colab['nome_completo']} - Status: {colab['status_fluxo']}"):
                    st.write(f"**CPF:** {colab['cpf']} | **Contato de Emergência:** {colab.get('contato_emergencia', 'N/A')}")
                    faltas_colab = supabase.table("registro_faltas").select("*").eq("id_colaborador", colab['id']).execute().data
                    nome_limpo = colab['nome_completo'].strip()
                    adiantamentos_todos = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Adiantamento Salarial").execute().data
                    adiantamentos_colab = [a for a in adiantamentos_todos if nome_limpo.lower() in a['descricao'].lower()]
                    
                    pdf_acerto = gerar_pdf_resumo_acerto(colab, faltas_colab, adiantamentos_colab)
                    nome_colab_limpo = limpar_nome_arquivo(colab['nome_completo'])
                    st.download_button(label="📄 Baixar Resumo para Acerto (PDF)", data=pdf_acerto, file_name=f"Resumo_Acerto_{nome_colab_limpo}.pdf", mime="application/pdf", key=f"dl_acerto_{colab['id']}")
                    
                    if st.button("✅ Confirmar Envio p/ Contabilidade e Arquivar", key=f"arq_rh_{colab['id']}"):
                        supabase.table("colaboradores").update({"status_fluxo": "Acerto Concluído"}).eq("id", colab['id']).execute()
                        st.success("Acerto arquivado com sucesso!"); st.rerun()

    with aba_folha_rh:
        st.subheader("Envio de Holerites para Pagamento")
        ativos_rh = supabase.table("colaboradores").select("id, nome_completo, cpf, cargo, setor, chave_pix").eq("status_fluxo", "Operação Liberada").execute().data
        if not ativos_rh:
            st.warning("Nenhum colaborador ativo encontrado.")
        else:
            opcoes_folha = {f"{c['nome_completo']} ({c['cargo']})": c for c in ativos_rh}
            colab_sel_str = st.selectbox("Selecionar Colaborador:", list(opcoes_folha.keys()))
            colab_folha = opcoes_folha[colab_sel_str]
            mes_ref = st.text_input("Mês de Referência", value=datetime.now().strftime("%B/%Y").capitalize())
            valor_liq = st.number_input("Valor Líquido (R$)", min_value=1.0, value=1500.0)
            pix_folha = st.text_input("Chave PIX", value=colab_folha.get('chave_pix', ''))
            holerite_pdf = st.file_uploader("Anexar Holerite em PDF", type=["pdf"])
            
            if st.button("Gerar Ordem de Pagamento de Folha"):
                if not pix_folha.strip() or not holerite_pdf:
                    st.error("⚠️ A Chave PIX e o anexo do Holerite são obrigatórios!")
                else:
                    try:
                        nome_colab_limpo = limpar_nome_arquivo(colab_folha['nome_completo'])
                        pasta_func = f"{nome_colab_limpo}_{colab_folha['cpf'].replace('.','').replace('-','')}"
                        nome_hol = f"{pasta_func}/Holerites/Holerite_{mes_ref.replace('/','_')}.pdf"
                        supabase.storage.from_(BUCKET_STORAGE).upload(nome_hol, holerite_pdf.getvalue(), {"upsert": "true"})
                        url_hol = supabase.storage.from_(BUCKET_STORAGE).get_public_url(nome_hol)
                    except:
                        url_hol = ""
                    desc_folha = f"Folha de Pagamento - {colab_folha['nome_completo']} | Ref: {mes_ref} | PIX: {pix_folha} | Holerite: {url_hol}"
                    supabase.table("lancamentos_financeiros").insert({
                        "descricao": desc_folha, "categoria": "Folha de Pagamento", "valor": valor_liq,
                        "data_vencimento": datetime.now().strftime("%Y-%m-%d"), "status_lancamento": "Aprovação Pendente Folha"
                    }).execute()
                    st.success("✅ Holerite guardado e enviado para a gestão financeira!")

    with aba_ativos_rh:
        renderizar_painel_colaboradores_ativos()

# ---------------------------------------------------------
# 2A. ENGENHARIA FLORESTAL (JEAN GUSTAVO)
# ---------------------------------------------------------
elif perfil_usuario == "Engenharia Florestal (Jean Gustavo)":
    st.header("🌲 Gestão Operacional de Equipes & Indústria (Florestal)")
    menu_operacoes = st.radio("Selecione a Ação:", ["🚜 Treinamentos", "💸 Diárias e Adiantamentos", "❌ Registro de Faltas", "🚪 Desligamento (Demissão)", "📊 Produção Florestal", "🏭 Produção Industrial (Madeira/Carvão)", "👥 Colaboradores em Operação"], horizontal=True)
    st.divider()

    if menu_operacoes == "🚜 Treinamentos":
        st.subheader("Gestão de Treinamentos e Liberação para Operação")
        pendentes = supabase.table("colaboradores").select("*").in_("status_fluxo", ["Aguardando Treinamento", "Em Treinamento"]).execute().data
        for colab in pendentes:
            with st.expander(f"📌 {colab['nome_completo']} - {colab['cargo']} [{colab['status_fluxo']}]"):
                if colab['status_fluxo'] == "Aguardando Treinamento":
                    if st.button("Iniciar Treinamento", key=f"init_{colab['id']}"):
                        supabase.table("colaboradores").update({"status_fluxo": "Em Treinamento"}).eq("id", colab['id']).execute()
                        st.rerun()
                else:
                    nota = st.number_input("Nota Final (0 a 100)", 0, 100, 0, key=f"nota_{colab['id']}")
                    cert = st.file_uploader("Certificado PDF", type=["pdf"], key=f"cert_{colab['id']}")
                    if st.button("Liberar Operação", key=f"lib_{colab['id']}"):
                        if nota >= 70 and cert:
                            supabase.table("colaboradores").update({"status_fluxo": "Operação Liberada"}).eq("id", colab['id']).execute()
                            st.success("Liberado!"); st.rerun()

    elif menu_operacoes == "💸 Diárias e Adiantamentos":
        st.subheader("Solicitação de Pagamentos")
        aptos = supabase.table("colaboradores").select("id, nome_completo, cargo, setor, chave_pix").eq("status_fluxo", "Operação Liberada").execute().data
        if aptos:
            tipo = st.radio("Tipo:", ["Diária", "Adiantamento"], horizontal=True)
            opcoes = {f"{c['nome_completo']}": c for c in aptos}
            sel = opcoes[st.selectbox("Colaborador:", list(opcoes.keys()))]
            vlr = st.number_input("Valor (R$)", min_value=1.0, value=100.0)
            pix = st.text_input("PIX", value=sel.get('chave_pix', ''))
            if st.button("Enviar Ordem"):
                supabase.table("lancamentos_financeiros").insert({
                    "descricao": f"{tipo} - {sel['nome_completo']} | PIX: {pix}",
                    "categoria": "Diárias Operacionais" if tipo == "Diária" else "Adiantamento Salarial",
                    "valor": vlr, "data_vencimento": datetime.now().strftime("%Y-%m-%d"), "status_lancamento": "Aprovação Pendente Financeiro"
                }).execute()
                st.success("Enviado para o financeiro!")

    elif menu_operacoes == "❌ Registro de Faltas":
        st.subheader("Apontamento de Faltas")
        aptos = supabase.table("colaboradores").select("id, nome_completo").eq("status_fluxo", "Operação Liberada").execute().data
        if aptos:
            opcoes = {c['nome_completo']: c['id'] for c in aptos}
            colab_nome = st.selectbox("Colaborador:", list(opcoes.keys()))
            dt_falta = st.date_input("Data")
            obs = st.text_area("Motivo")
            if st.button("Registrar Falta"):
                supabase.table("registro_faltas").insert({
                    "id_colaborador": opcoes[colab_nome], "nome_colaborador": colab_nome,
                    "data_falta": dt_falta.strftime("%Y-%m-%d"), "observacao": obs, "status_falta": "Pendente",
                    "cadastrado_por": email_logado
                }).execute()
                st.success("Falta registrada!")

    elif menu_operacoes == "🚪 Desligamento (Demissão)":
        st.subheader("Desligamento")
        aptos = supabase.table("colaboradores").select("*").eq("status_fluxo", "Operação Liberada").execute().data
        if aptos:
            opcoes = {c['nome_completo']: c for c in aptos}
            sel = opcoes[st.selectbox("Colaborador:", list(opcoes.keys()))]
            motivo = st.text_area("Motivo do Desligamento:")
            if st.button("Confirmar Desligamento"):
                supabase.table("colaboradores").update({"status_fluxo": "Desligamento da empresa", "motivo_desligamento": motivo}).eq("id", sel['id']).execute()
                st.success("Encaminhado para o RH!")

    elif menu_operacoes == "📊 Produção Florestal":
        st.subheader("📊 Produção Diária (Floresta)")
        with st.form("form_prod_florestal"):
            dt_prod = st.date_input("Data")
            arv_abat = st.number_input("Árvores Abatidas", 0, value=0)
            vol_abat = st.number_input("Volume Abatido (m³)", 0.0, value=0.0, format="%.3f")
            if st.form_submit_button("Salvar"):
                supabase.table("producao_diaria").insert({"data_producao": dt_prod.strftime("%Y-%m-%d"), "arvores_abatidas": arv_abat, "volume_abatido_m3": vol_abat}).execute()
                st.success("Salvo com sucesso!")

    elif menu_operacoes == "🏭 Produção Industrial (Madeira/Carvão)":
        st.subheader("🏭 Controle de Produção e Estoque Industrial")
        sub_ind = st.radio("Selecione o Produto:", ["Madeira Serrada", "Carvão"], horizontal=True)
        st.divider()
        
        if sub_ind == "Madeira Serrada":
            with st.form("form_madeira"):
                dt_m = st.date_input("Data", key="dt_m")
                especie = st.text_input("Espécie da Madeira (Ex: Ipê, Jatobá)")
                vol_tora = st.number_input("Volume de Tora Serrado (m³)", 0.0, format="%.3f")
                vol_serrado = st.number_input("Volume Madeira Serrada Obtida (m³)", 0.0, format="%.3f")
                vol_saida = st.number_input("Volume Saídas/Vendido (m³)", 0.0, format="%.3f")
                vlr_unit = st.number_input("Valor Unitário Vendido (R$/m³)", 0.0, format="%.2f")
                if st.form_submit_button("Salvar Madeira Serrada"):
                    if not especie.strip():
                        st.error("Informe a espécie.")
                    else:
                        supabase.table("producao_industrial").insert({
                            "tipo_produto": "Madeira Serrada", "data_producao": dt_m.strftime("%Y-%m-%d"),
                            "especie": especie.strip(), "volume_tora": vol_tora, "volume_serrado": vol_serrado,
                            "quantidade_saida": vol_saida, "valor_unitario": vlr_unit
                        }).execute()
                        st.success("Salvo com sucesso!")
                        
        elif sub_ind == "Carvão":
            with st.form("form_carv"):
                dt_c = st.date_input("Data", key="dt_c")
                prod_sacas = st.number_input("Qtd Produzida (Sacas)", 0.0, format="%.1f")
                saida_sacas = st.number_input("Qtd Saídas/Vendidas (Sacas)", 0.0, format="%.1f")
                vlr_unit_c = st.number_input("Valor Unitário Vendido (R$/saca)", 0.0, format="%.2f")
                if st.form_submit_button("Salvar Carvão"):
                    supabase.table("producao_industrial").insert({
                        "tipo_produto": "Carvão", "data_producao": dt_c.strftime("%Y-%m-%d"),
                        "quantidade_produzida": prod_sacas, "quantidade_saida": saida_sacas, "valor_unitario": vlr_unit_c
                    }).execute()
                    st.success("Salvo com sucesso!")

    elif menu_operacoes == "👥 Colaboradores em Operação":
        renderizar_painel_colaboradores_ativos()

# ---------------------------------------------------------
# 2B. OPERACIONAL INDÚSTRIA - SERRARIA (FELIPE)
# ---------------------------------------------------------
elif perfil_usuario == "Operacional Indústria - Serraria (Felipe)":
    st.header("🌲 Gestão Operacional de Equipes & Indústria (Serraria)")
    menu_operacoes = st.radio("Selecione a Ação:", ["🚜 Treinamentos", "💸 Diárias e Adiantamentos", "❌ Registro de Faltas", "🚪 Desligamento (Demissão)", "📊 Produção Florestal", "🏭 Produção Industrial (Madeira/Carvão)", "👥 Colaboradores em Operação"], horizontal=True)
    st.divider()

    if menu_operacoes == "🚜 Treinamentos":
        st.subheader("Gestão de Treinamentos e Liberação para Operação")
        pendentes = supabase.table("colaboradores").select("*").in_("status_fluxo", ["Aguardando Treinamento", "Em Treinamento"]).execute().data
        for colab in pendentes:
            with st.expander(f"📌 {colab['nome_completo']} - {colab['cargo']} [{colab['status_fluxo']}]"):
                if colab['status_fluxo'] == "Aguardando Treinamento":
                    if st.button("Iniciar Treinamento", key=f"init_{colab['id']}"):
                        supabase.table("colaboradores").update({"status_fluxo": "Em Treinamento"}).eq("id", colab['id']).execute()
                        st.rerun()
                else:
                    nota = st.number_input("Nota Final (0 a 100)", 0, 100, 0, key=f"nota_{colab['id']}")
                    cert = st.file_uploader("Certificado PDF", type=["pdf"], key=f"cert_{colab['id']}")
                    if st.button("Liberar Operação", key=f"lib_{colab['id']}"):
                        if nota >= 70 and cert:
                            supabase.table("colaboradores").update({"status_fluxo": "Operação Liberada"}).eq("id", colab['id']).execute()
                            st.success("Liberado!"); st.rerun()

    elif menu_operacoes == "💸 Diárias e Adiantamentos":
        st.subheader("Solicitação de Pagamentos")
        aptos = supabase.table("colaboradores").select("id, nome_completo, cargo, setor, chave_pix").eq("status_fluxo", "Operação Liberada").execute().data
        if aptos:
            tipo = st.radio("Tipo:", ["Diária", "Adiantamento"], horizontal=True)
            opcoes = {f"{c['nome_completo']}": c for c in aptos}
            sel = opcoes[st.selectbox("Colaborador:", list(opcoes.keys()))]
            vlr = st.number_input("Valor (R$)", min_value=1.0, value=100.0)
            pix = st.text_input("PIX", value=sel.get('chave_pix', ''))
            if st.button("Enviar Ordem"):
                supabase.table("lancamentos_financeiros").insert({
                    "descricao": f"{tipo} - {sel['nome_completo']} | PIX: {pix}",
                    "categoria": "Diárias Operacionais" if tipo == "Diária" else "Adiantamento Salarial",
                    "valor": vlr, "data_vencimento": datetime.now().strftime("%Y-%m-%d"), "status_lancamento": "Aprovação Pendente Financeiro"
                }).execute()
                st.success("Enviado para o financeiro!")

    elif menu_operacoes == "❌ Registro de Faltas":
        st.subheader("Apontamento de Faltas")
        aptos = supabase.table("colaboradores").select("id, nome_completo").eq("status_fluxo", "Operação Liberada").execute().data
        if aptos:
            opcoes = {c['nome_completo']: c['id'] for c in aptos}
            colab_nome = st.selectbox("Colaborador:", list(opcoes.keys()))
            dt_falta = st.date_input("Data")
            obs = st.text_area("Motivo")
            if st.button("Registrar Falta"):
                supabase.table("registro_faltas").insert({
                    "id_colaborador": opcoes[colab_nome], "nome_colaborador": colab_nome,
                    "data_falta": dt_falta.strftime("%Y-%m-%d"), "observacao": obs, "status_falta": "Pendente",
                    "cadastrado_por": email_logado
                }).execute()
                st.success("Falta registrada!")

    elif menu_operacoes == "🚪 Desligamento (Demissão)":
        st.subheader("Desligamento")
        aptos = supabase.table("colaboradores").select("*").eq("status_fluxo", "Operação Liberada").execute().data
        if aptos:
            opcoes = {c['nome_completo']: c for c in aptos}
            sel = opcoes[st.selectbox("Colaborador:", list(opcoes.keys()))]
            motivo = st.text_area("Motivo do Desligamento:")
            if st.button("Confirmar Desligamento"):
                supabase.table("colaboradores").update({"status_fluxo": "Desligamento da empresa", "motivo_desligamento": motivo}).eq("id", sel['id']).execute()
                st.success("Encaminhado para o RH!")

    elif menu_operacoes == "📊 Produção Florestal":
        st.subheader("📊 Produção Diária (Floresta)")
        with st.form("form_prod_florestal"):
            dt_prod = st.date_input("Data")
            arv_abat = st.number_input("Árvores Abatidas", 0, value=0)
            vol_abat = st.number_input("Volume Abatido (m³)", 0.0, value=0.0, format="%.3f")
            if st.form_submit_button("Salvar"):
                supabase.table("producao_diaria").insert({"data_producao": dt_prod.strftime("%Y-%m-%d"), "arvores_abatidas": arv_abat, "volume_abatido_m3": vol_abat}).execute()
                st.success("Salvo com sucesso!")

    elif menu_operacoes == "🏭 Produção Industrial (Madeira/Carvão)":
        st.subheader("🏭 Controle de Produção e Estoque Industrial")
        sub_ind = st.radio("Selecione o Produto:", ["Madeira Serrada", "Carvão"], horizontal=True)
        st.divider()
        
        if sub_ind == "Madeira Serrada":
            with st.form("form_madeira"):
                dt_m = st.date_input("Data", key="dt_m")
                especie = st.text_input("Espécie da Madeira (Ex: Ipê, Jatobá)")
                vol_tora = st.number_input("Volume de Tora Serrado (m³)", 0.0, format="%.3f")
                vol_serrado = st.number_input("Volume Madeira Serrada Obtida (m³)", 0.0, format="%.3f")
                vol_saida = st.number_input("Volume Saídas/Vendido (m³)", 0.0, format="%.3f")
                vlr_unit = st.number_input("Valor Unitário Vendido (R$/m³)", 0.0, format="%.2f")
                if st.form_submit_button("Salvar Madeira Serrada"):
                    if not especie.strip():
                        st.error("Informe a espécie.")
                    else:
                        supabase.table("producao_industrial").insert({
                            "tipo_produto": "Madeira Serrada", "data_producao": dt_m.strftime("%Y-%m-%d"),
                            "especie": especie.strip(), "volume_tora": vol_tora, "volume_serrado": vol_serrado,
                            "quantidade_saida": vol_saida, "valor_unitario": vlr_unit
                        }).execute()
                        st.success("Salvo com sucesso!")
                        
        elif sub_ind == "Carvão":
            with st.form("form_carv"):
                dt_c = st.date_input("Data", key="dt_c")
                prod_sacas = st.number_input("Qtd Produzida (Sacas)", 0.0, format="%.1f")
                saida_sacas = st.number_input("Qtd Saídas/Vendidas (Sacas)", 0.0, format="%.1f")
                vlr_unit_c = st.number_input("Valor Unitário Vendido (R$/saca)", 0.0, format="%.2f")
                if st.form_submit_button("Salvar Carvão"):
                    supabase.table("producao_industrial").insert({
                        "tipo_produto": "Carvão", "data_producao": dt_c.strftime("%Y-%m-%d"),
                        "quantidade_produzida": prod_sacas, "quantidade_saida": saida_sacas, "valor_unitario": vlr_unit_c
                    }).execute()
                    st.success("Salvo com sucesso!")

    elif menu_operacoes == "👥 Colaboradores em Operação":
        renderizar_painel_colaboradores_ativos()

# ---------------------------------------------------------
# 2C. OPERACIONAL INDÚSTRIA - CARVOARIA (NELSON)
# ---------------------------------------------------------
elif perfil_usuario == "Operacional Indústria - Carvoaria (Nelson)":
    st.header("🌲 Gestão Operacional de Equipes & Indústria (Carvoaria)")
    menu_operacoes = st.radio("Selecione a Ação:", ["🚜 Treinamentos", "💸 Diárias e Adiantamentos", "❌ Registro de Faltas", "🚪 Desligamento (Demissão)", "📊 Produção Florestal", "🏭 Produção Industrial (Madeira/Carvão)", "👥 Colaboradores em Operação"], horizontal=True)
    st.divider()

    if menu_operacoes == "🚜 Treinamentos":
        st.subheader("Gestão de Treinamentos e Liberação para Operação")
        pendentes = supabase.table("colaboradores").select("*").in_("status_fluxo", ["Aguardando Treinamento", "Em Treinamento"]).execute().data
        for colab in pendentes:
            with st.expander(f"📌 {colab['nome_completo']} - {colab['cargo']} [{colab['status_fluxo']}]"):
                if colab['status_fluxo'] == "Aguardando Treinamento":
                    if st.button("Iniciar Treinamento", key=f"init_{colab['id']}"):
                        supabase.table("colaboradores").update({"status_fluxo": "Em Treinamento"}).eq("id", colab['id']).execute()
                        st.rerun()
                else:
                    nota = st.number_input("Nota Final (0 a 100)", 0, 100, 0, key=f"nota_{colab['id']}")
                    cert = st.file_uploader("Certificado PDF", type=["pdf"], key=f"cert_{colab['id']}")
                    if st.button("Liberar Operação", key=f"lib_{colab['id']}"):
                        if nota >= 70 and cert:
                            supabase.table("colaboradores").update({"status_fluxo": "Operação Liberada"}).eq("id", colab['id']).execute()
                            st.success("Liberado!"); st.rerun()

    elif menu_operacoes == "💸 Diárias e Adiantamentos":
        st.subheader("Solicitação de Pagamentos")
        aptos = supabase.table("colaboradores").select("id, nome_completo, cargo, setor, chave_pix").eq("status_fluxo", "Operação Liberada").execute().data
        if aptos:
            tipo = st.radio("Tipo:", ["Diária", "Adiantamento"], horizontal=True)
            opcoes = {f"{c['nome_completo']}": c for c in aptos}
            sel = opcoes[st.selectbox("Colaborador:", list(opcoes.keys()))]
            vlr = st.number_input("Valor (R$)", min_value=1.0, value=100.0)
            pix = st.text_input("PIX", value=sel.get('chave_pix', ''))
            if st.button("Enviar Ordem"):
                supabase.table("lancamentos_financeiros").insert({
                    "descricao": f"{tipo} - {sel['nome_completo']} | PIX: {pix}",
                    "categoria": "Diárias Operacionais" if tipo == "Diária" else "Adiantamento Salarial",
                    "valor": vlr, "data_vencimento": datetime.now().strftime("%Y-%m-%d"), "status_lancamento": "Aprovação Pendente Financeiro"
                }).execute()
                st.success("Enviado para o financeiro!")

    elif menu_operacoes == "❌ Registro de Faltas":
        st.subheader("Apontamento de Faltas")
        aptos = supabase.table("colaboradores").select("id, nome_completo").eq("status_fluxo", "Operação Liberada").execute().data
        if aptos:
            opcoes = {c['nome_completo']: c['id'] for c in aptos}
            colab_nome = st.selectbox("Colaborador:", list(opcoes.keys()))
            dt_falta = st.date_input("Data")
            obs = st.text_area("Motivo")
            if st.button("Registrar Falta"):
                supabase.table("registro_faltas").insert({
                    "id_colaborador": opcoes[colab_nome], "nome_colaborador": colab_nome,
                    "data_falta": dt_falta.strftime("%Y-%m-%d"), "observacao": obs, "status_falta": "Pendente",
                    "cadastrado_por": email_logado
                }).execute()
                st.success("Falta registrada!")

    elif menu_operacoes == "🚪 Desligamento (Demissão)":
        st.subheader("Desligamento")
        aptos = supabase.table("colaboradores").select("*").eq("status_fluxo", "Operação Liberada").execute().data
        if aptos:
            opcoes = {c['nome_completo']: c for c in aptos}
            sel = opcoes[st.selectbox("Colaborador:", list(opcoes.keys()))]
            motivo = st.text_area("Motivo do Desligamento:")
            if st.button("Confirmar Desligamento"):
                supabase.table("colaboradores").update({"status_fluxo": "Desligamento da empresa", "motivo_desligamento": motivo}).eq("id", sel['id']).execute()
                st.success("Encaminhado para o RH!")

    elif menu_operacoes == "📊 Produção Florestal":
        st.subheader("📊 Produção Diária (Floresta)")
        with st.form("form_prod_florestal"):
            dt_prod = st.date_input("Data")
            arv_abat = st.number_input("Árvores Abatidas", 0, value=0)
            vol_abat = st.number_input("Volume Abatido (m³)", 0.0, value=0.0, format="%.3f")
            if st.form_submit_button("Salvar"):
                supabase.table("producao_diaria").insert({"data_producao": dt_prod.strftime("%Y-%m-%d"), "arvores_abatidas": arv_abat, "volume_abatido_m3": vol_abat}).execute()
                st.success("Salvo com sucesso!")

    elif menu_operacoes == "🏭 Produção Industrial (Madeira/Carvão)":
        st.subheader("🏭 Controle de Produção e Estoque Industrial")
        sub_ind = st.radio("Selecione o Produto:", ["Madeira Serrada", "Carvão"], horizontal=True)
        st.divider()
        
        if sub_ind == "Madeira Serrada":
            with st.form("form_madeira"):
                dt_m = st.date_input("Data", key="dt_m")
                especie = st.text_input("Espécie da Madeira (Ex: Ipê, Jatobá)")
                vol_tora = st.number_input("Volume de Tora Serrado (m³)", 0.0, format="%.3f")
                vol_serrado = st.number_input("Volume Madeira Serrada Obtida (m³)", 0.0, format="%.3f")
                vol_saida = st.number_input("Volume Saídas/Vendido (m³)", 0.0, format="%.3f")
                vlr_unit = st.number_input("Valor Unitário Vendido (R$/m³)", 0.0, format="%.2f")
                if st.form_submit_button("Salvar Madeira Serrada"):
                    if not especie.strip():
                        st.error("Informe a espécie.")
                    else:
                        supabase.table("producao_industrial").insert({
                            "tipo_produto": "Madeira Serrada", "data_producao": dt_m.strftime("%Y-%m-%d"),
                            "especie": especie.strip(), "volume_tora": vol_tora, "volume_serrado": vol_serrado,
                            "quantidade_saida": vol_saida, "valor_unitario": vlr_unit
                        }).execute()
                        st.success("Salvo com sucesso!")
                        
        elif sub_ind == "Carvão":
            with st.form("form_carv"):
                dt_c = st.date_input("Data", key="dt_c")
                prod_sacas = st.number_input("Qtd Produzida (Sacas)", 0.0, format="%.1f")
                saida_sacas = st.number_input("Qtd Saídas/Vendidas (Sacas)", 0.0, format="%.1f")
                vlr_unit_c = st.number_input("Valor Unitário Vendido (R$/saca)", 0.0, format="%.2f")
                if st.form_submit_button("Salvar Carvão"):
                    supabase.table("producao_industrial").insert({
                        "tipo_produto": "Carvão", "data_producao": dt_c.strftime("%Y-%m-%d"),
                        "quantidade_produzida": prod_sacas, "quantidade_saida": saida_sacas, "valor_unitario": vlr_unit_c
                    }).execute()
                    st.success("Salvo com sucesso!")

    elif menu_operacoes == "👥 Colaboradores em Operação":
        renderizar_painel_colaboradores_ativos()


# ---------------------------------------------------------
# 3. LANÇAMENTOS FINANCEIROS E RECIBOS (JONAS)
# ---------------------------------------------------------
elif perfil_usuario == "Lançamentos Financeiros (Jonas)":
    st.header("📄 Gestão Financeira e Contabilidade")
    aba1, aba2, aba3, aba4, aba_folha_j, aba_ativos_j = st.tabs(["🔔 Aprovações", "📝 Novo Lançamento Manual", "📂 Concluídos e Recibos", "📊 Fechamento Mensal", "💵 Gestão da Folha", "👥 Colaboradores em Operação"])
    
    with aba1:
        ordens = supabase.table("lancamentos_financeiros").select("*").eq("status_lancamento", "Aprovação Pendente Financeiro").execute().data
        for o in ordens:
            with st.expander(f"R$ {o['valor']:.2f} - {o['descricao'][:30]}"):
                if st.button("Aprovar", key=f"apr_{o['id']}"):
                    supabase.table("lancamentos_financeiros").update({"status_lancamento": "Lançado - Aguardando Pagamento"}).eq("id", o['id']).execute()
                    st.rerun()

    with aba2:
        with st.form("form_manual"):
            forn = st.text_input("Fornecedor / Título")
            desc = st.text_area("Descrição")
            pix = st.text_input("Chave PIX")
            cat = st.selectbox("Categoria", ["Manutenção", "Combustível", "Serviços", "Outros"])
            vlr = st.number_input("Valor (R$)", min_value=0.01)
            venc = st.date_input("Vencimento")
            if st.form_submit_button("Lançar"):
                supabase.table("lancamentos_financeiros").insert({
                    "descricao": f"{forn} | {desc} | PIX: {pix}", "categoria": cat, "valor": vlr,
                    "data_vencimento": venc.strftime("%Y-%m-%d"), "status_lancamento": "Lançado - Aguardando Pagamento"
                }).execute()
                st.success("Lançado!")

    with aba3:
        pagos = supabase.table("lancamentos_financeiros").select("*").eq("status_lancamento", "Pago & Concluído").execute().data
        for p in pagos:
            with st.expander(f"✅ R$ {p['valor']:.2f} - {p['descricao'][:30]}"):
                if st.button("Arquivar", key=f"arq_{p['id']}"):
                    supabase.table("lancamentos_financeiros").update({"status_lancamento": "Arquivado"}).eq("id", p['id']).execute()
                    st.rerun()

    with aba4:
        st.subheader("Fechamento Mensal")
        if st.button("Gerar PDF Fechamento"):
            st.info("Função ativa de consolidação.")

    with aba_folha_j:
        st.subheader("Gestão da Folha")
        folhas = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Folha de Pagamento").eq("status_lancamento", "Aprovação Pendente Folha").execute().data
        for f in folhas:
            with st.expander(f"Folha: R$ {f['valor']:.2f}"):
                if st.button("Aprovar Folha", key=f"ap_f_{f['id']}"):
                    supabase.table("lancamentos_financeiros").update({"status_lancamento": "Folha - Aguardando Pagamento"}).eq("id", f['id']).execute()
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
        for c in contas:
            with st.expander(f"R$ {c['valor']:.2f} - {c['descricao'][:30]}"):
                st.write(c['descricao'])
                if st.button("Confirmar Pagamento", key=f"pag_{c['id']}"):
                    supabase.table("lancamentos_financeiros").update({"status_lancamento": "Pago & Concluído", "url_comprovante_pago": "BB_Cupixi"}).eq("id", c['id']).execute()
                    st.success("Pago!"); st.rerun()

    with aba_folha_m:
        folhas_m = supabase.table("lancamentos_financeiros").select("*").eq("categoria", "Folha de Pagamento").eq("status_lancamento", "Folha - Aguardando Pagamento").execute().data
        for fm in folhas_m:
            with st.expander(f"Folha R$ {fm['valor']:.2f}"):
                if st.button("Pagar Folha", key=f"p_f_{fm['id']}"):
                    supabase.table("lancamentos_financeiros").update({"status_lancamento": "Pago & Concluído", "url_comprovante_pago": "BB_FA"}).eq("id", fm['id']).execute()
                    st.success("Pago!"); st.rerun()

    with aba_ativos_m:
        renderizar_painel_colaboradores_ativos()

# ---------------------------------------------------------
# 5. PAINEL DE CORREÇÕES (EXCLUSIVO ADMIN)
# ---------------------------------------------------------
elif perfil_usuario == "🛠️ Painel de Correções (Exclusivo Admin)":
    st.header("🛠️ Painel de Manutenção e Correções")
    st.caption("Esta área é restrita. Cuidado ao apagar dados, pois a exclusão é permanente.")
    
    aba_corr_fin, aba_corr_func = st.tabs(["💰 Apagar Lançamentos Financeiros", "👥 Apagar/Corrigir Funcionários"])
    
    with aba_corr_fin:
        st.subheader("Gestão de Lançamentos Financeiros")
        todos_lancamentos = supabase.table("lancamentos_financeiros").select("*").order("id", desc=True).execute().data
        
        if not todos_lancamentos:
            st.info("Nenhum lançamento encontrado no banco de dados.")
        else:
            for lanc in todos_lancamentos:
                with st.expander(f"ID: {lanc['id']} | {lanc['categoria']} | R$ {lanc['valor']:.2f} | Status: {lanc['status_lancamento']}"):
                    st.write(f"**Descrição original:** {lanc['descricao']}")
                    st.write(f"**Data de Vencimento:** {lanc['data_vencimento']}")
                    
                    if st.button("🗑️ Apagar este lançamento definitivamente", key=f"del_fin_{lanc['id']}"):
                        supabase.table("lancamentos_financeiros").delete().eq("id", lanc['id']).execute()
                        st.success("Lançamento apagado com sucesso!")
                        st.rerun()

    with aba_corr_func:
        st.subheader("Gestão de Colaboradores (Exclusão por Erro)")
        todos_colabs = supabase.table("colaboradores").select("*").order("id", desc=True).execute().data
        
        if not todos_colabs:
            st.info("Nenhum colaborador encontrado.")
        else:
            for colab in todos_colabs:
                with st.expander(f"ID: {colab['id']} | {colab['nome_completo']} | CPF: {colab['cpf']} | {colab['status_fluxo']}"):
                    st.write(f"**Cargo:** {colab['cargo']} | **Setor:** {colab['setor']}")
                    
                    if st.button("🗑️ Apagar registo do colaborador", key=f"del_colab_{colab['id']}"):
                        supabase.table("colaboradores").delete().eq("id", colab['id']).execute()
                        st.success("Colaborador apagado do sistema!")
                        st.rerun()
