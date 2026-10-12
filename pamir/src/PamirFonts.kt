package com.v2ray.ang.pamir

import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import com.v2ray.ang.R

/** Mognu display face (Unbounded, OFL): brand name, screen titles and the mascot's lines. */
val MognuDisplay = FontFamily(
    Font(R.font.mognu_display_bold, FontWeight.ExtraBold),
    Font(R.font.mognu_display, FontWeight.Black),
)

/** Mognu text face (Onest, OFL): everything that is not a title. */
val MognuText = FontFamily(
    Font(R.font.mognu_text_regular, FontWeight.Normal),
    Font(R.font.mognu_text_semibold, FontWeight.SemiBold),
    Font(R.font.mognu_text_bold, FontWeight.Bold),
    Font(R.font.mognu_text_extrabold, FontWeight.ExtraBold),
)
