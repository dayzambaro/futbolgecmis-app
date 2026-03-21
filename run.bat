@echo off
echo ================================================
echo  Sırali Skor Eslesme Analizi - Baslatiliyor...
echo ================================================
cd /d "%~dp0"
python -m pip install -r requirements.txt -q
python -m streamlit run app.py
pause
