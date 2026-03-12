@echo off
echo ================================================
echo  Sırali Skor Eslesme Analizi - Baslatiliyor...
echo ================================================
cd /d "%~dp0"
pip install -r requirements.txt -q
streamlit run app.py
pause
