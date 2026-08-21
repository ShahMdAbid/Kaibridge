1. Global & Utility Functions
These are standalone functions not attached to a specific class instance.
BaseType
BoardLayerFromLegacyId
BOX2ISafe
Cast_to_BOARD
Cast_to_BOARD_ITEM
Cast_to_FOOTPRINT
Cast_to_PAD
Cast_to_PCB_ARC
Cast_to_PCB_BARCODE
Cast_to_PCB_DIM_ALIGNED
Cast_to_PCB_DIM_CENTER
Cast_to_PCB_DIM_LEADER
Cast_to_PCB_DIM_ORTHOGONAL
Cast_to_PCB_DIM_RADIAL
Cast_to_PCB_GROUP
Cast_to_PCB_MARKER
Cast_to_PCB_REFERENCE_IMAGE
Cast_to_PCB_SHAPE
Cast_to_PCB_TABLE
Cast_to_PCB_TEXT
Cast_to_PCB_TEXTBOX
Cast_to_PCB_TARGET
Cast_to_PCB_TRACK
Cast_to_PCB_VIA
Cast_to_SHAPE_ARC
Cast_to_SHAPE_CIRCLE
Cast_to_SHAPE_COMPOUND
Cast_to_SHAPE_LINE_CHAIN
Cast_to_SHAPE_POLY_SET
Cast_to_SHAPE_RECT
Cast_to_SHAPE_SEGMENT
Cast_to_SHAPE_SIMPLE
Cast_to_ZONE
colorRefs
CopperLayerToOrdinal
CreateEmptyBoard
DescribeRef
DoubleValueFromString
EDAItemFlagsToString
EnsureFileDirectoryExists
EnsureFileExtension
ExpandEnvVarSubstitutions
ExpandTextVars
ExportFootprintsToLibrary
ExportSpecctraDSN
ExportVRML
FetchUnitsFromString
FlipLayer
FocusOnItem
FootprintDelete
FootprintEnumerate
FootprintIsWritable
FootprintLibCreate
FootprintLibDelete
FootprintLoad
FootprintSave
FormatAngle
FormatInternalUnits
FromMils
FromMM
FromUserUnit
FullVersion
GetBaseVersion
GetBoard
GetBuildDate
GetBuildVersion
GetCanonicalFieldName
GetColorSettings
GetCommitHash
GetCurrentSelection
GetDefaultFieldName
GetDefaultPlotExtension
GetFootprintLibraries
GetFootprints
GetFlippedAlignment
GetGeneratedFieldDisplayName
GetLabel
GetLanguage
GetMajorMinorPatchTuple
GetMajorMinorPatchVersion
GetMajorMinorVersion
GetNetnameLayer
GetPlatformGetBitnessName
GetPluginForPath
GetScaleForInternalUnitType
GetSemanticVersion
GetSettingsManager
GetText
GetUserFieldName
GetUserUnits
GetUnLoadableWizards
GetVersionInfoData
GetWizardsBackTrace
GetWizardsSearchPaths
ImportSpecctraSES
InvokeCopperZonesEditor
InvokeNonCopperZonesEditor
InvokeRuleAreaEditor
IsActionRunning
IsBackLayer
IsClearanceLayer
IsCopperLayer
IsCopperLayerLowerThan
IsDCodeLayer
IsEeschemaType
IsExternalCopperLayer
IsFrontLayer
IsGeneratedField
IsGerbviewType
IsHoleLayer
IsImperialUnit
IsInnerCopperLayer
IsInstantiableType
IsMetricUnit
IsMiscType
IsNetnameLayer
IsNightlyVersion
IsNonCopperLayer
IsNullType
IsPadCopperLayer
IsPageLayoutEditorType
IsPcbLayer
IsPcbnewType
IsPointsLayer
IsSolderMaskLayer
IsTypeCorrect
IsUserLayer
IsUTF8
IsViaCopperLayer
IsViaPadLayer
IsValidLayer
IsZoneFillLayer
JoinExtensions
KiROUND
LayerName
LoadBoard
LoadPluginModule
LoadPlugins
Map3DLayerToPCBLayer
MapPCBLayerTo3DLayer
MessageTextFromMinOptMax
MessageTextFromValue
Mils2IU
Mils2mm
Mm2mils
new_clone
NewBoard
NilUuid
PlotDrawingSheet
PrintZoneConnection
PutOnGridMils
PutOnGridMM
Refresh
ResolveTextVars
ResolveUriByEnvVars
SafeReadFile
SaveBoard
SearchHelpFileFullPath
set_class_attr
set_instance_attr
SetOpenGLBackendInfo
SetOpenGLInfo
SHAPE_TYPE_asString
StringFromValue
ToGalLayer
ToHAlignment
ToLAYER_ID
ToMils
ToMM
ToUserUnit
UpdateUserInterface
ValueFromString
VECTOR2I_Mils
VECTOR2I_MM
Version
WarnUserIfOperatingSystemUnsupported
wrapper
WriteDRCReport
wxGetDefaultPyEncoding
wxPointMils
wxPointMM
wxRectMils
wxRectMM
wxSetDefaultPyEncoding
wxSizeMils
wxSizeMM
_swig_add_metaclass
_swig_repr
_swig_setattr_nondynamic_class_variable
_swig_setattr_nondynamic_instance_variable
2. Classes and their Methods
ActionPlugin
__init__, defaults, GetCategoryName, GetClassName, GetDescription, GetIconFileName, GetName, GetShowToolbarButton, Run
ARC_MID
__init__, __swig_destroy__
base_seqVect
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
BASE_SET
__init__, __swig_destroy__
BOARD
__init__, __swig_destroy__, AddArea, AddListener, AddNative, AddVariant, AllConnectedItems, BoardOutline, BuildConnectivity, BuildListOfNets, BulkRemoveStaleTeardrops, CacheItemById, CacheTriangulation, ClassOf, ClearProject, ComputeBoundingBox, ConvertBrdLayerToPolygonalContours, ConvertCrossReferencesToKIIDs, ConvertKIIDsToCrossReferences, DeleteAllFootprints, DeleteMARKERs, DeleteVariant, DetachAllFootprints, DpCoupledNet, Drawings, FillItemMap, FinalizeBulkAdd, FinalizeBulkRemove, FindFootprintByPath, FindFootprintByReference, FindNet, FixupEmbeddedData, FlipLayer, Footprints, Generators, GetAllNetClasses, GetArea, GetAreaCount, GetBoardEdgesBoundingBox, GetBoardPolygonOutlines, GetBoardUse, GetClass, GetConnectivity, GetContextualTextVars, GetCopperLayerCount, GetCopperLayerStackMaxId, GetCurrentNetClassName, GetCurrentVariant, GetDesignSettings, GetDrawings, GetEmbeddedFiles, GetEnabledLayers, GetFileFormatVersionAtLoad, GetFileName, GetFirstFootprint, GetFonts, GetFootprints, GetGenerator, GetHighLightNetCodes, GetItemByIdCache, GetItemSet, GetLayerID, GetLayerName, GetLayerType, GetLengthCalculation, GetMaxClearanceValue, GetNetClasses, GetNetcodeFromNetname, GetNetClassAssignmentCandidates, GetNetInfo, GetNetsByName, GetNetsByNetcode, GetNodesCount, GetOutlinesChainingEpsilon, GetPad, GetPads, GetPageSettings, GetPlotOptions, GetProject, GetProperties, GetSortedPadListByXthenYCoord, GetStackupOrDefault, GetStandardLayerName, GetTimeStamp, GetTitleBlock, GetTrackLength, GetTracks, GetTrackWidthList, GetUserDefinedLayerCount, GetUserUnits, GetVariantDescription, GetVariantNames, GetVariantNamesForUI, GetViasDimensionsList, GetVisibleElements, GetVisibleLayers, GetZoneList, Groups, GroupsSanityCheck, GroupsSanityCheckInternal, HasItemsOnLayer, HasVariant, HighLightOFF, HighLightON, IncrementTimeStamp, InitializeClearanceCache, InvalidateClearanceCache, IsElementVisible, IsEmpty, IsFootprintHolder, IsFootprintLayerVisible, IsHighLightNetON, IsLayerEnabled, IsLayerVisible, LayerDepth, LegacyTeardrops, MapNets, Markers, MatchDpSuffix, OnItemChanged, OnItemsChanged, OnItemsCompositeUpdate, OnRatsnestChanged, Points, ProjectElementType, RecordDRCExclusions, RemoveAll, RemoveAllItemsOnLayer, RemoveAllListeners, RemoveListener, RemoveNative, RemoveUnusedNets, RenameVariant, ResetNetHighLight, ResolveDRCExclusions, ResolveItem, ResolveTextVar, RunOnNestedEmbeddedFiles, SanitizeNetcodes, Save, SaveToHistory, SetAreasNetCodesFromNetNames, SetBoardUse, SetCopperLayerCount, SetCurrentVariant, SetDesignSettings, SetElementVisibility, SetEmbeddedFilesDelegate, SetEnabledLayers, SetFileFormatVersionAtLoad, SetFileName, SetGenerator, SetHighLightNet, SetLayerDescr, SetLayerName, SetLayerType, SetLegacyTeardrops, SetOutlinesChainingEpsilon, SetPageSettings, SetPlotOptions, SetProject, SetProperties, SetTitleBlock, SetUserDefinedLayerCount, SetUserUnits, SetVariantDescription, SetVariantNames, SetVisibleAlls, SetVisibleElements, SetVisibleLayers, SynchronizeComponentClasses, SynchronizeNetsAndNetClasses, SynchronizeProperties, SynchronizeTuningProfileProperties, TestZoneIntersection, Tracks, TracksInNet, UncacheItemById, UpdateBoardOutline, UpdateRatsnestExclusions, UpdateUserUnits, Zones
BOARD_CONNECTED_ITEM
__init__, __swig_destroy__, ClassOf, GetClearanceOverrides, GetDisplayNetname, GetEffectiveNetClass, GetLocalClearance, GetLocalRatsnestVisible, GetNet, GetNetClassName, GetNetCode, GetNetname, GetNetnameMsg, GetOwnClearance, GetShortNetname, GetTeardropAllowSpanTwoTracks, GetTeardropBestLengthRatio, GetTeardropBestWidthRatio, GetTeardropCurved, GetTeardropMaxLength, GetTeardropMaxTrackWidth, GetTeardropMaxWidth, GetTeardropParams, GetTeardropPreferZoneConnections, GetTeardropsEnabled, PackNet, SetLocalRatsnestVisible, SetNet, SetNetCode, SetTeardropAllowSpanTwoTracks, SetTeardropBestLengthRatio, SetTeardropBestWidthRatio, SetTeardropCurved, SetTeardropMaxLength, SetTeardropMaxTrackWidth, SetTeardropMaxWidth, SetTeardropsEnabled, SetTeardropPreferZoneConnections, UnpackNet
BOARD_DESIGN_SETTINGS
__eq__, __init__, __ne__, __swig_destroy__, CloneFrom, GetAuxOrigin, GetBiggestClearanceValue, GetBoardThickness, GetCurrentDiffPairGap, GetCurrentDiffPairViaGap, GetCurrentDiffPairWidth, GetCurrentNetClassName, GetCurrentTrackWidth, GetCurrentViaDrill, GetCurrentViaSize, GetCustomDiffPairGap, GetCustomDiffPairViaGap, GetCustomDiffPairWidth, GetCustomTrackWidth, GetCustomViaDrill, GetCustomViaSize, GetDefaultZoneSettings, GetDiffPairIndex, GetDRCEpsilon, GetEnabledLayers, GetGridOrigin, GetHolePlatingThickness, GetLayerClass, GetLineThickness, GetSeverity, GetSmallestClearanceValue, GetStackupDescriptor, GetTeadropParamsList, GetTextItalic, GetTextSize, GetTextThickness, GetTextUpright, GetTrackWidthIndex, GetUserDefinedLayerCount, GetViaSizeIndex, Ignore, IsLayerEnabled, LoadFromFile, SetAuxOrigin, SetBoardThickness, SetCopperLayerCount, SetCustomDiffPairGap, SetCustomDiffPairViaGap, SetCustomDiffPairWidth, SetCustomTrackWidth, SetCustomViaDrill, SetCustomViaSize, SetDefaultMasterPad, SetDefaultZoneSettings, SetDiffPairIndex, SetEnabledLayers, SetGridOrigin, SetTrackWidthIndex, SetUserDefinedLayerCount, SetViaSizeIndex, UseCustomDiffPairDimensions, UseCustomTrackViaSize, UseNetClassDiffPair, UseNetClassTrack, UseNetClassVia
BOARD_ITEM
__eq__, __init__, __swig_destroy__, BoardCopperLayerCount, BoardLayerCount, BoardLayerSet, Cast, CopyFrom, DeleteStructure, Duplicate, Flip, GetBoard, GetCenter, GetEffectiveHoleShape, GetEffectiveShape, GetFontMetrics, GetFPRelativePosition, GetLayer, GetLayerName, GetLayerSet, GetMaxError, GetParent, GetParentAsString, GetParentFootprint, GetStroke, GetX, GetY, HasDrilledHole, HasHole, HasLineStroke, IsConnected, IsGroupableType, IsKnockout, IsOnCopperLayer, IsOnLayer, IsSideSpecific, IsTented, LayerMaskDescribe, Mirror, Move, Normalize, NormalizeForCompare, Rotate, RunOnChildren, SetFPRelativePosition, SetIsKnockout, SetLayer, SetLayerSet, SetPos, SetStartEnd, SetStroke, SetX, SetY, Similarity, StyleFromSettings, SwapItemData, TransformShapeToPolygon, TransformShapeToPolySet
BOARD_ITEM_CONTAINER
__init__, __swig_destroy__, Add, AddNative, Delete, DeleteNative, Remove, RemoveNative
BOARD_LISTENER
__init__, __swig_destroy__, OnBoardCompositeUpdate, OnBoardHighlightNetChanged, OnBoardItemAdded, OnBoardItemChanged, OnBoardItemRemoved, OnBoardItemsAdded, OnBoardItemsChanged, OnBoardItemsRemoved, OnBoardNetSettingsChanged, OnBoardRatsnestChanged
BOX2I
__eq__, __init__, __ne__, __swig_destroy__, ByCenter, ByCorners, Centre, Contains, Diagonal, Distance, FarthestPointTo, Format, GetArea, GetBottom, GetBoundingBoxRotated, GetCenter, GetEnd, GetHeight, GetInflated, GetLeft, GetOrigin, GetPosition, GetRight, GetSize, GetSizeMax, GetTop, GetWidth, GetWithOffset, GetX, GetY, Inflate, Intersect, Intersects, IntersectsCircle, IntersectsCircleEdge, IsValid, Merge, Move, NearestPoint, Normalize, Offset, SetEnd, SetHeight, SetMaximum, SetOrigin, SetSize, SetWidth, SetX, SetY, SquaredDiagonal, SquaredDistance
CLIPPER_Z_VALUE
__init__, __swig_destroy__
cmp_drawings
__call__, __init__, __swig_destroy__
cmp_pads
__call__, __init__, __swig_destroy__
cmp_zones
__call__, __init__, __swig_destroy__
CN_DISJOINT_NET_ENTRY
__init__, __swig_destroy__
COLOR4D
__init__, __swig_destroy__, Brighten, Brightened, Compare, ContrastRatio, Darken, Darkened, Desaturate, Distance, FindNearestLegacyColor, FromCSSRGBA, FromHSL, FromHSV, GetBrightness, Invert, Inverted, LegacyMix, Mix, RelativeLuminance, Saturate, SetFromHexString, SetFromWxString, ToColour, ToCSSString, ToHexString, ToHSL, ToHSV, WithAlpha
CONNECTIVITY_DATA
__init__, __swig_destroy__, Add, BlockRatsnestItems, Build, ClearLocalRatsnest, ClearRatsnest, ComputeLocalRatsnest, FillIsolatedIslandsMap, GetConnectedItems, GetConnectedItemsAtAnchor, GetConnectedPads, GetConnectedPadsAndVias, GetConnectedTracks, GetConnectivityAlgo, GetFromToCache, GetLocalRatsnest, GetLock, GetNetCount, GetNetItems, GetNetNameForNetCode, GetNetSettings, GetNodeCount, GetPadCount, GetRatsnestForNet, GetUnconnectedCount, HasNetNameForNetCode, HideLocalRatsnest, IsConnectedOnLayer, MarkItemNetAsDirty, Move, PropagateNets, RecalculateRatsnest, RefreshNetcodeMap, Remove, RemoveInvalidRefs, RunOnUnconnectedEdges, SetProgressReporter, TestTrackEndpointDangling, Update
D356_RECORD
__init__, __swig_destroy__
DELETED_BOARD_ITEM
__eq__, __init__, __swig_destroy__, GetClass, GetInstance
DIFF_PAIR_DIMENSION
__eq__, __init__, __lt__, __ne__, __swig_destroy__
DRAWINGS
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, pop_front, push_back, push_front, rbegin, rend, reserve, resize, size, swap
DRILL_PRECISION
__init__, __swig_destroy__, GetPrecisionString
DRILL_SPAN
__init__, __lt__, __swig_destroy__, BottomLayer, DrillEndLayer, DrillStartLayer, Pair, TopLayer
DRILL_TOOL
__init__, __swig_destroy__
EDA_ANGLE
__abs__, __add__, __iadd__, __init__, __isub__, __mul__, __rmul__, __sub__, __swig_destroy__, __truediv__, Arccos, Arcsin, Arctan, Arctan2, AsDegrees, AsRadians, AsTenthsOfADegree, Cos, Invert, IsCardinal, IsCardinal90, IsHorizontal, IsParallelTo, IsVertical, IsZero, KeepUpright, Normalize, Normalize180, Normalize720, Normalize90, Normalized, NormalizeNegative, Round, Sin, Tan
EDA_GROUP
__init__, __swig_destroy__, AddItem, AsEdaItem, GetDesignBlockLibId, GetGroupMemberIds, GetItems, GetName, HasDesignBlockLink, RemoveAll, RemoveItem, SetDesignBlockLibId, SetName
EDA_ITEM
__init__, __lt__, __swig_destroy__, ClearBrightened, ClearEditFlags, ClearFlags, ClearSelected, ClearTempFlags, Clone, DisambiguateItemDescription, GetBoundingBox, GetClass, GetEditFlags, GetEmbeddedFiles, GetEmbeddedFonts, GetFlags, GetFocusPosition, GetFriendlyName, GetItemDescription, GetMenuImage, GetMsgPanelInfo, GetParent, GetParentGroup, GetParentGroupId, GetPosition, GetRolloverPos, GetSortPosition, GetTempFlags, GetTypeDesc, HasFlag, HitTest, IsBrightened, IsEntered, IsForceVisible, IsLocked, IsModified, IsMoving, IsNew, IsReplaceable, IsRollover, IsSelected, IsShownAsBitmap, IsType, Matches, PyGetClass, RenderAsBitmap, Replace, SetBrightened, SetFlags, SetForceVisible, SetIsRollover, SetIsShownAsBitmap, SetLocked, SetModified, SetParent, SetParentGroup, SetPosition, SetSelected, Sort, Type, ViewBBox, ViewGetLayers, Visit, XorFlags
EDA_IU_SCALE
__init__, __swig_destroy__, IUToMils, IUTomm, MilsToIU, mmToIU
EDA_SHAPE
__eq__, __init__, __swig_destroy__, CalcArcAngles, Compare, Deserialize, EndsSwapped, GetArcAngle, GetArcMid, GetBezierC1, GetBezierC2, GetBezierPoints, GetBotRight, GetCornerRadius, GetCornersInSequence, GetEffectiveWidth, GetEnd, GetEndX, GetEndY, GetFillColor, GetFillMode, GetFillModeProp, GetHatchedFill, GetHatching, GetHatchLineSpacing, GetHatchLineWidth, GetHatchLines, GetLength, GetLineColor, GetLineStyle, GetPointCount, GetPolyPoints, GetPolyShape, GetRadius, GetRectangleHeight, GetRectangleWidth, GetRectCorners, GetSegmentAngle, GetShape, GetStart, GetStartX, GetStartY, GetTopLeft, GetWidth, IsAnyFill, IsClockwiseArc, IsClosed, IsFilledForHitTesting, IsPolyShapeValid, IsProxyItem, IsSolidFill, MakeEffectiveShapes, MakeEffectiveShapesForHitTesting, RebuildBezierToSegmentsPointsList, Serialize, SetArcAngleAndEnd, SetArcGeometry, SetBezierC1, SetBezierC2, SetBottom, SetCachedArcData, SetCenter, SetCenterX, SetCenterY, SetCornerRadius, SetEnd, SetEndX, SetEndY, SetFillColor, SetFilled, SetFillMode, SetFillModeProp, SetHatchingDirty, SetIsProxyItem, SetLeft, SetLineColor, SetLineStyle, SetPolyPoints, SetPolyShape, SetRadius, SetRectangle, SetRectangleHeight, SetRectangleWidth, SetRight, SetShape, SetStart, SetStartX, SetStartY, SetTop, SetWidth, ShapeGetMsgPanelInfo, SHAPE_T_asString, ShowShape, Similarity, SwapShape, TransformShapeToPolygon, UpdateHatching
EDA_SHAPE_HATCH_CACHE_DATA
__init__, __swig_destroy__
EDA_TEXT
__eq__, __gt__, __init__, __lt__, __swig_destroy__, AddRenderCacheGlyph, ClearBoundingBoxCache, ClearRenderCache, Compare, CopyText, Deserialize, Empty, EvaluateText, FlipHJustify, Format, GetAttributes, GetAutoThickness, GetDrawFont, GetDrawPos, GetDrawRotation, GetEffectiveTextPenWidth, GetEffectiveTextShape, GetFont, GetFontName, GetFontProp, GetHorizJustify, GetHyperlink, GetInterline, GetLinePositions, GetLineSpacing, GetRenderCache, GetShownText, GetText, GetTextAngle, GetTextAngleDegrees, GetTextBox, GetTextColor, GetTextHeight, GetTextPos, GetTextSize, GetTextStyleName, GetTextThickness, GetTextThicknessProperty, GetTextWidth, GetVertJustify, GotoPageHref, HasHyperlink, HasTextVars, IsBold, IsDefaultFormatting, IsGotoPageHref, IsItalic, IsKeepUpright, IsMirrored, IsMultilineAllowed, IsVisible, Levenshtein, MapHorizJustify, MapVertJustify, Offset, Print, RemoveHyperlink, Replace, ResolveFont, Serialize, SetActiveUrl, SetAttributes, SetAutoThickness, SetBold, SetBoldFlag, SetFont, SetFontProp, SetHorizJustify, SetHyperlink, SetItalic, SetItalicFlag, SetKeepUpright, SetLineSpacing, SetMirrored, SetMultilineAllowed, SetText, SetTextAngle, SetTextAngleDegrees, SetTextColor, SetTextHeight, SetTextPos, SetTextSize, SetTextThickness, SetTextWidth, SetTextX, SetTextY, SetUnresolvedFontName, SetVertJustify, SetVisible, SetupRenderCache, Similarity, SwapAttributes, SwapText, TextHitTest, ValidateHyperlink
EXCELLON_WRITER
__init__, __swig_destroy__, CreateDrillandMapFilesSet, GetOffset, SetFormat, SetOptions, SetRouteModeForOvalHoles
EXPORTER_VRML
__init__, __swig_destroy__, ExportVRML_File
FILE_LINE_READER
__init__, __swig_destroy__, CurPos, FileLength, Rewind
FILE_OUTPUTFORMATTER
__init__, __swig_destroy__
FilePlugin
__init__
FOOTPRINT
__eq__, __init__, __swig_destroy__, Add3DModel, AddNative, AddNetTiePadGroup, AddVariant, AllowMissingCourtyard, AllowSolderMaskBridges, ApplyDefaultSettings, AutoPositionFields, BuildCourtyardCaches, BuildNetTieCache, CheckClippedSilk, CheckFootprintAttributes, CheckNetTiePadGroups, CheckNetTies, CheckPads, CheckShortingPads, ClassOf, ClearAllNets, ClearNetTiePadGroups, ClearTransientComponentClassNames, CoverageRatio, DeleteVariant, Deserialize, Duplicate, DuplicateItem, FindPadByNumber, FixUpPadsForBoard, FixUuids, GetArea, GetAttributes, GetBoundingBox, GetBoundingHull, GetCachedCourtyard, GetClass, GetClearanceOverrides, GetComponentClass, GetComponentClassAsString, GetContextualTextVars, GetCourtyard, GetCoverageArea, GetDesc, GetDNPForVariant, GetDuplicatePadNumbersAreJumpers, GetEffectiveShape, GetEmbeddedFiles, GetExcludedFromBOMForVariant, GetExcludedFromPosFilesForVariant, GetField, GetFields, GetFieldsShownText, GetFieldsText, GetFieldShownText, GetFieldText, GetFieldValueForVariant, GetFileFormatVersionAtLoad, GetFilters, GetFlag, GetFonts, GetFootprint, GetFPID, GetFPIDAsString, GetFpPadsLocalBbox, GetInitialComments, GetJumperPadGroup, GetKeywords, GetLayerBoundingBox, GetLIB_ID, GetLibDescription, GetLibNickname, GetLikelyAttribute, GetLink, GetLocalClearance, GetLocalSolderMaskMargin, GetLocalSolderPasteMargin, GetLocalSolderPasteMarginRatio, GetLocalZoneConnection, GetName, GetNetTieCache, GetNetTiePadGroups, GetNetTiePads, GetNextFieldOrdinal, GetNextPadNumber, GetOrientation, GetOrientationDegrees, GetPad, GetPadCount, GetPads, GetPath, GetPinCount, GetPrivateLayers, GetReference, GetReferenceAsString, GetSearchTerms, GetSheetfile, GetSheetname, GetSide, GetStackupLayers, GetStackupMode, GetStaticComponentClass, GetTransientComponentClassNames, GetTypeName, GetUniquePadCount, GetUniquePadNumbers, GetUnitInfo, GetValue, GetValueAsString, GetVariant, GetVariants, GetZoneConnectionOverrides, GraphicalItems, Groups, HasField, HasThroughHolePads, HasVariant, HitTest, HitTestAccurate, HitTestOnLayer, IncrementFlag, IncrementReference, InvalidateComponentClassCache, InvalidateGeometryCaches, IsBoardOnly, IsConflicting, IsDNP, IsExcludedFromBOM, IsExcludedFromPosFiles, IsFlipped, IsLibNameValid, IsNetTie, IsPlaced, JumperPadGroups, LegacyPadsLocked, MapPadNumbersToNetTieGroups, Models, MoveAnchorPosition, NeedsPlaced, Pads, Points, RecomputeComponentClass, Reference, RemoveNative, RenameVariant, ResolveComponentClassNames, ResolveTextVar, Serialize, SetAllowMissingCourtyard, SetAllowSolderMaskBridges, SetAttributes, SetBoardOnly, SetDNP, SetDuplicatePadNumbersAreJumpers, SetExcludedFromBOM, SetExcludedFromPosFiles, SetField, SetFields, SetFileFormatVersionAtLoad, SetFilters, SetFlag, SetFPID, SetFPIDAsString, SetInitialComments, SetIsPlaced, SetKeywords, SetLayerAndFlip, SetLibDescription, SetLink, SetLocalClearance, SetLocalSolderMaskMargin, SetLocalSolderPasteMargin, SetLocalSolderPasteMarginRatio, SetLocalZoneConnection, SetNeedsPlaced, SetOrientation, SetOrientationDegrees, SetPath, SetPrivateLayers, SetReference, SetSheetfile, SetSheetname, SetStackupLayers, SetStackupMode, SetStaticComponentClass, SetTransientComponentClassNames, SetUnitInfo, SetValue, SetVariant, StringLibNameInvalidChars, TextOnly, TransformFPShapesToPolySet, TransformFPTextToPolySet, TransformPadsToPolySet, Value, ViewGetLOD, Zones
FOOTPRINT_COURTYARD_CACHE_DATA
__init__, __swig_destroy__
FOOTPRINT_GEOMETRY_CACHE_DATA
__init__, __swig_destroy__
FOOTPRINT_VARIANT
__eq__, __init__, __swig_destroy__, GetDNP, GetExcludedFromBOM, GetExcludedFromPosFiles, GetFields, GetFieldValue, GetName, HasFieldValue, SetDNP, SetExcludedFromBOM, SetExcludedFromPosFiles, SetFieldValue, SetName
FOOTPRINTS
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, pop_front, push_back, push_front, rbegin, rend, reserve, resize, size, swap
FootprintWizardParameter
__init__, __str__, AddError, Check, ClearErrors, DefaultValue, SetValue
FootprintWizardPlugin
__init__, AddParam, AnyErrors, BuildFootprint, CheckParam, defaults, GetBuildMessages, GetDescription, GetFootprint, GetImage, GetName, GetNumParameterPages, GetParam, GetParameterDesignators, GetParameterErrors, GetParameterHints, GetParameterNames, GetParameterPageName, GetParametersByPageIndex, GetParametersByPageName, GetParameterTypes, GetParameterValues, GetReferencePrefix, GetValue, ResetWizard, SetParameterValues, Show
FP_3DMODEL
__eq__, __init__, __swig_destroy__
FP_CACHE
__init__, __swig_destroy__, Exists, GetFootprints, GetPath, GetTimestamp, IsModified, IsPath, IsWritable, Load, Remove, Save, SetPath
FP_CACHE_ENTRY
__init__, __swig_destroy__, GetFileName, GetFootprint, SetFilePath
FP_UNIT_INFO
__init__, __swig_destroy__
GAL_SET
__init__, __swig_destroy__, Contains, DefaultVisible, Seq, set
GENDRILL_WRITER_BASE
__init__, __swig_destroy__, CreateMapFilesSet, GenDrillReportFile, GetDrillFileExt, GetOffset, SetMapFileFormat, SetMergeOption, SetPageInfo
GENERATORS
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, pop_front, push_back, push_front, rbegin, rend, reserve, resize, size, swap
GERBER_JOBFILE_WRITER
__init__, __swig_destroy__, AddGbrFile, CreateJobFile, WriteJSONJobFile
GERBER_WRITER
__init__, __swig_destroy__, CreateDrillandMapFilesSet, SetFormat, SetOptions
GROUPS
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, pop_front, push_back, push_front, rbegin, rend, reserve, resize, size, swap
HIGH_LIGHT_INFO
__init__, __swig_destroy__
HOLE_INFO
__init__, __swig_destroy__
INPUTSTREAM_LINE_READER
__init__, __swig_destroy__
intVector
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
IO_ERROR
__init__, __swig_destroy__, init, Problem, what, What, Where
IPC356D_WRITER
__init__, __swig_destroy__, SetDoNotExportUnconnectedPads, Write
ISOLATED_ISLANDS
__init__, __swig_destroy__
JOBFILE_PARAMS
__init__, __swig_destroy__
KI_PARAM_ERROR
__init__, __swig_destroy__, What
KiCadPlugin
__init__, deregister, GetPluginPath, register
KIID
__eq__, __gt__, __init__, __lt__, __ne__, __swig_destroy__, AsLegacyTimestamp, AsLegacyTimestampString, AsStdString, AsString, Clone, Combine, ConvertTimestampToUuid, CreateNilUuids, Hash, Increment, IsLegacyTimestamp, SeedGenerator, SniffTest
KIID_NIL_SET_RESET
__init__, __swig_destroy__
KIID_PATH
__eq__, __gt__, __iadd__, __init__, __lt__, __swig_destroy__, AsString, EndsWith, MakeRelativeTo
KIID_VECT_LIST
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
LAYER
__init__, __swig_destroy__, clear, ParseType, ShowType
LAYERS_CHECKED
__init__, __swig_destroy__
LIB_ID
__eq__, __gt__, __init__, __lt__, __ne__, __swig_destroy__, clear, compare, empty, FindIllegalLibraryNameChar, FixIllegalChars, Format, GetFullLibraryName, GetLibItemName, GetLibNickname, GetSubLibraryName, GetUniStringLibId, GetUniStringLibItemName, GetUniStringLibNickname, GetUniStringSubLibraryName, HasIllegalChars, IsLegacy, IsValid, Parse, SetLibItemName, SetLibNickname, SetSubLibraryName
LINE_READER
__init__, __swig_destroy__, GetSource, Length, Line, LineNumber, ReadLine
LSEQ
__init__, __swig_destroy__, TestLayers
LSET
__init__, __swig_destroy__, AddLayer, addLayer, AddLayerSet, addLayerSet, AllBoardTechMask, AllCuMask, AllLayersMask, AllNonCuMask, AllTechMask, BackAssembly, BackBoardTechMask, BackMask, BackTechMask, ClearCopperLayers, ClearNonCopperLayers, ClearUserDefinedLayers, Contains, ContainsAll, CuStack, ExternalCuMask, ExtractLayer, FlipStandardLayers, FmtBin, FmtHex, FrontAssembly, FrontBoardTechMask, FrontMask, FrontTechMask, InternalCuMask, IsBetween, LayerCount, Name, NameToLayer, ParseHex, PhysicalLayersMask, RemoveLayer, removeLayer, RemoveLayerSet, removeLayerSet, RunOnLayers, Seq, SeqStackupForPlotting, SeqStackupTop2Bottom, SideSpecificMask, TechAndUserUIOrder, UIOrder, UserDefinedLayersMask, UserMask
MAP_STRING_STRING
__bool__, __contains__, __delitem__, __getitem__, __init__, __iter__, __len__, __nonzero__, __setitem__, __swig_destroy__, asdict, begin, clear, count, empty, end, erase, find, get_allocator, has_key, items, iteritems, iterkeys, iterator, itervalues, key_iterator, keys, lower_bound, rbegin, rend, size, swap, upper_bound, value_iterator, values
MARKER_BASE
__init__, __swig_destroy__, GetBoundingBoxMarker, GetComment, GetPos, GetRCItem, GetSeverity, GetUUID, HitTestMarker, IsExcluded, MarkerScale, SetExcluded, SetMarkerScale, SetMarkerType, ShapeToPolygon
MARKERS
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
NET_SETTINGS
__eq__, __init__, __ne__, __swig_destroy__, AppendNetclassLabelAssignment, ClearAllCaches, ClearCacheForNet, ClearNetclasses, ClearNetclassLabelAssignment, ClearNetclassLabelAssignments, ClearNetclassPatternAssignments, ClearNetColorAssignments, ForEachBusMember, GetCachedEffectiveNetClass, GetCompositeNetclasses, GetDefaultNetclass, GetEffectiveNetClass, GetNetclassByName, GetNetclasses, GetNetclassLabelAssignments, GetNetclassPatternAssignments, GetNetColorAssignments, HasEffectiveNetClass, HasNetclass, HasNetclassLabelAssignment, ParseBusGroup, ParseBusVector, RecomputeEffectiveNetclasses, SetDefaultNetclass, SetNetclass, SetNetclasses, SetNetclassLabelAssignment, SetNetclassPatternAssignment, SetNetclassPatternAssignments, SetNetColorAssignment
NETCLASS
__eq__, __init__, __swig_destroy__, ContainsNetclassWithName, Deserialize, GetBusWidth, GetBusWidthOpt, GetBusWidthParent, GetClass, GetClearance, GetClearanceOpt, GetClearanceParent, GetConstituentNetclasses, GetDescription, GetDiffPairGap, GetDiffPairGapOpt, GetDiffPairGapParent, GetDiffPairViaGap, GetDiffPairViaGapOpt, GetDiffPairViaGapParent, GetDiffPairWidth, GetDiffPairWidthOpt, GetDiffPairWidthParent, GetHumanReadableName, GetLineStyle, GetLineStyleOpt, GetLineStyleParent, GetName, GetPcbColor, GetPcbColorParent, GetPriority, GetSchematicColor, GetSchematicColorParent, GetTrackWidth, GetTrackWidthOpt, GetTrackWidthParent, GetTuningProfile, GetTuningProfileParent, GetuViaDiameter, GetuViaDiameterOpt, GetuViaDiameterParent, GetuViaDrill, GetuViaDrillOpt, GetuViaDrillParent, GetViaDiameter, GetViaDiameterOpt, GetViaDiameterParent, GetViaDrill, GetViaDrillOpt, GetViaDrillParent, GetWireWidth, GetWireWidthOpt, GetWireWidthParent, HasBusWidth, HasClearance, HasDiffPairGap, HasDiffPairViaGap, HasDiffPairWidth, HasLineStyle, HasPcbColor, HasTrackWidth, HasTuningProfile, HasuViaDiameter, HasuViaDrill, HasViaDiameter, HasViaDrill, HasWireWidth, IsDefault, ResetParameters, ResetParents, Serialize, SetBusWidth, SetBusWidthParent, SetClearance, SetClearanceParent, SetConstituentNetclasses, SetDescription, SetDiffPairGap, SetDiffPairGapParent, SetDiffPairViaGap, SetDiffPairViaGapParent, SetDiffPairWidth, SetDiffPairWidthParent, SetLineStyle, SetLineStyleParent, SetName, SetPcbColor, SetPcbColorParent, SetPriority, SetSchematicColor, SetSchematicColorParent, SetTrackWidth, SetTrackWidthParent, SetTuningProfile, SetTuningProfileParent, SetuViaDiameter, SetuViaDiameterParent, SetuViaDrill, SetuViaDrillParent, SetViaDiameter, SetViaDiameterParent, SetViaDrill, SetViaDrillParent, SetWireWidth, SetWireWidthParent
netclasses_map
__bool__, __contains__, __delitem__, __getitem__, __init__, __iter__, __len__, __nonzero__, __setitem__, __swig_destroy__, asdict, begin, clear, count, empty, end, erase, find, get_allocator, has_key, items, iteritems, iterkeys, iterator, itervalues, key_iterator, keys, lower_bound, rbegin, rend, size, swap, upper_bound, value_iterator, values
NETCODES_MAP
__bool__, __contains__, __delitem__, __getitem__, __init__, __iter__, __len__, __nonzero__, __setitem__, __swig_destroy__, asdict, begin, clear, count, empty, end, erase, find, get_allocator, has_key, items, iteritems, iterkeys, iterator, itervalues, key_iterator, keys, lower_bound, rbegin, rend, size, swap, upper_bound, value_iterator, values
NETINFO_ITEM
__init__, __swig_destroy__, ClassOf, Clear, GetClass, GetDisplayNetname, GetNetClass, GetNetClassName, GetNetClassSlow, GetNetCode, GetNetname, GetParent, GetShortNetname, HasAutoGeneratedNetname, IsCurrent, SetIsCurrent, SetNetClass, SetNetCode, SetNetname, SetParent
NETINFO_LIST
__init__, __swig_destroy__, GetNetCount, GetNetItem, GetParent, NetsByName, NetsByNetcode, OrphanedItem, RebuildDisplayNetnames
NETNAMES_MAP
__bool__, __contains__, __delitem__, __getitem__, __init__, __iter__, __len__, __nonzero__, __setitem__, __swig_destroy__, asdict, begin, clear, count, empty, end, erase, find, get_allocator, has_key, items, iteritems, iterkeys, iterator, itervalues, key_iterator, keys, lower_bound, rbegin, rend, size, swap, upper_bound, value_iterator, values
OUTPUTFORMATTER
__init__, __swig_destroy__, Finish, GetQuoteChar, Print, Quotes, Quotew
PAD
__eq__, __init__, __swig_destroy__, AddPrimitive, AddPrimitivePoly, AddPrimitiveShape, ApertureMask, AppendPrimitives, BuildEffectivePolygon, BuildEffectiveShapes, CanFlashLayer, CanHaveNumber, CheckPad, ClassOf, ClearSecondaryDrillSize, ClearTertiaryDrillSize, ClearZoneLayerOverrides, ClonePad, Compare, ConditionallyFlashed, ConnSMDMask, DeletePrimitivesList, Deserialize, FlashLayer, FlipPrimitives, GetAnchorPadShape, GetAttribute, GetBackdrillEndLayer, GetBackdrillMode, GetBackdrillSize, GetBackPostMachining, GetBackPostMachiningAngle, GetBackPostMachiningDepth, GetBackPostMachiningMode, GetBackPostMachiningSize, GetBottomBackdrillLayer, GetBottomBackdrillSize, GetBoundingBox, GetBoundingRadius, GetChamferPositions, GetChamferRectRatio, GetClass, GetCustomShapeAsPolygon, GetCustomShapeInZoneOpt, GetDelta, GetDrillShape, GetDrillSize, GetDrillSizeX, GetDrillSizeY, GetEffectivePolygon, GetEffectiveShape, GetFPRelativeOrientation, GetFrontPostMachining, GetFrontPostMachiningAngle, GetFrontPostMachiningDepth, GetFrontPostMachiningMode, GetFrontPostMachiningSize, GetFrontRoundRectRadiusRatio, GetFrontRoundRectRadiusSize, GetFrontShape, GetKeepTopBottom, GetLocalClearance, GetLocalSolderMaskMargin, GetLocalSolderPasteMargin, GetLocalSolderPasteMarginRatio, GetLocalSpokeWidthOverride, GetLocalThermalGapOverride, GetLocalThermalSpokeWidthOverride, GetLocalZoneConnection, GetName, GetNumber, GetOffset, GetOrientation, GetOrientationDegrees, GetOwnClearance, GetPadName, GetPadToDieDelay, GetPadToDieLength, GetPinFunction, GetPinType, GetPrimaryDrillCapped, GetPrimaryDrillCappedFlag, GetPrimaryDrillEndLayer, GetPrimaryDrillFilled, GetPrimaryDrillFilledFlag, GetPrimaryDrillShape, GetPrimaryDrillSize, GetPrimaryDrillSizeX, GetPrimaryDrillSizeY, GetPrimaryDrillStartLayer, GetPrimitives, GetPrincipalLayer, GetProperty, GetRemoveUnconnected, GetRoundRectCornerRadius, GetRoundRectRadiusRatio, GetSecondaryDrillEndLayer, GetSecondaryDrillShape, GetSecondaryDrillSize, GetSecondaryDrillSizeX, GetSecondaryDrillSizeY, GetSecondaryDrillStartLayer, GetShape, GetSize, GetSizeX, GetSizeY, GetSolderMaskExpansion, GetSolderPasteMargin, GetSubRatsnest, GetTertiaryDrillEndLayer, GetTertiaryDrillShape, GetTertiaryDrillSize, GetTertiaryDrillSizeX, GetTertiaryDrillSizeY, GetTertiaryDrillStartLayer, GetThermalGap, GetThermalSpokeAngle, GetThermalSpokeAngleDegrees, GetTopBackdrillLayer, GetTopBackdrillSize, GetUnconnectedLayerMode, GetZoneConnectionOverrides, GetZoneLayerOverride, HasExplicitDefinitionForLayer, HitTest, ImportSettingsFrom, IsAperturePad, IsBackdrilledOrPostMachined, IsDirty, IsFlipped, IsFreePad, IsNoConnectPad, IsNPTHWithNoCopper, MergePrimitivesAsPolygon, Padstack, PTHMask, Recombine, ReplacePrimitives, SameLogicalPadAs, Serialize, SetAnchorPadShape, SetAttribute, SetBackdrillEndLayer, SetBackdrillMode, SetBackdrillSize, SetBackPostMachining, SetBackPostMachiningAngle, SetBackPostMachiningDepth, SetBackPostMachiningMode, SetBackPostMachiningSize, SetBottomBackdrillLayer, SetBottomBackdrillSize, SetChamferPositions, SetChamferRectRatio, SetCustomShapeInZoneOpt, SetDelta, SetDirty, SetDrillShape, SetDrillSize, SetDrillSizeX, SetDrillSizeY, SetFPRelativeOrientation, SetFrontPostMachining, SetFrontPostMachiningAngle, SetFrontPostMachiningDepth, SetFrontPostMachiningMode, SetFrontPostMachiningSize, SetFrontRoundRectRadiusRatio, SetFrontRoundRectRadiusSize, SetFrontShape, SetKeepTopBottom, SetLocalClearance, SetLocalSolderMaskMargin, SetLocalSolderPasteMargin, SetLocalSolderPasteMarginRatio, SetLocalThermalGapOverride, SetLocalThermalSpokeWidthOverride, SetLocalZoneConnection, SetName, SetNumber, SetOffset, SetOrientation, SetOrientationDegrees, SetPadName, SetPadstack, SetPadToDieDelay, SetPadToDieLength, SetPinFunction, SetPinType, SetPrimaryDrillCapped, SetPrimaryDrillCappedFlag, SetPrimaryDrillEndLayer, SetPrimaryDrillFilled, SetPrimaryDrillFilledFlag, SetPrimaryDrillShape, SetPrimaryDrillSize, SetPrimaryDrillSizeX, SetPrimaryDrillSizeY, SetPrimaryDrillStartLayer, SetProperty, SetRemoveUnconnected, SetRoundRectCornerRadius, SetRoundRectRadiusRatio, SetSecondaryDrillEndLayer, SetSecondaryDrillShape, SetSecondaryDrillSize, SetSecondaryDrillSizeX, SetSecondaryDrillSizeY, SetSecondaryDrillStartLayer, SetShape, SetSize, SetSizeX, SetSizeY, SetSubRatsnest, SetTertiaryDrillEndLayer, SetTertiaryDrillShape, SetTertiaryDrillSize, SetTertiaryDrillSizeX, SetTertiaryDrillSizeY, SetTertiaryDrillStartLayer, SetThermalGap, SetThermalSpokeAngle, SetThermalSpokeAngleDegrees, SetTopBackdrillLayer, SetTopBackdrillSize, SetUnconnectedLayerMode, SetX, SetY, SetZoneLayerOverride, ShapePos, SharesNetTieGroup, ShowLegacyPadShape, ShowPadAttr, ShowPadShape, SMDMask, SwapShapePositions, TransformHoleToPolygon, TransformShapeToPolygon, UnplatedHoleMask, ViewGetLOD
PADS
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, pop_front, push_back, push_front, rbegin, rend, reserve, resize, size, swap
PADS_VEC
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
PADSTACK
__eq__, __init__, __ne__, __swig_destroy__, AnchorShape, BackOuterLayers, BackPostMachining, ChamferPositions, ChamferRatio, Clearance, ClearPrimitives, Compare, CopperLayer, CustomName, CustomShapeInZoneMode, DefaultThermalSpokeAngleForShape, Deserialize, Drill, DrillShape, EffectiveLayerFor, EndLayer, FlipLayers, ForEachUniqueLayer, FrontOuterLayers, FrontPostMachining, GetBackdrillEndLayer, GetBackdrillMode, GetBackdrillSize, GetOrientation, HasExplicitDefinitionForLayer, IsCapped, IsCovered, IsFilled, IsPlugged, IsTented, LayerSet, Mode, Name, Offset, Primitives, RelevantShapeLayers, RoundRectRadius, RoundRectRadiusRatio, SecondaryDrill, Serialize, SetAnchorShape, SetBackdrillEndLayer, SetBackdrillMode, SetBackdrillSize, SetChamferPositions, SetChamferRatio, SetCustomName, SetCustomShapeInZoneMode, SetDrillShape, SetLayerSet, SetMode, SetOrientation, SetRoundRectRadius, SetRoundRectRadiusRatio, SetShape, SetSize, SetThermalSpokeAngle, SetUnconnectedLayerMode, Shape, Similarity, Size, SolderMaskMargin, SolderPasteMargin, SolderPasteMarginRatio, StartLayer, TertiaryDrill, ThermalGap, ThermalSpokeAngle, ThermalSpokeWidth, TrapezoidDeltaSize, UnconnectedLayerMode, UniqueLayers, ZoneConnection
PCB_ARC
__eq__, __init__, __swig_destroy__, ClassOf, Deserialize, GetAngle, GetArcAngleEnd, GetArcAngleStart, GetClass, GetEffectiveShape, GetMid, GetRadius, HitTest, IsCCW, IsDegenerated, Serialize, SetMid
PCB_BARCODE
__eq__, __init__, __swig_destroy__, AssembleBarcode, ClassOf, Compare, ComputeBarcode, ComputeTextPoly, Deserialize, GetAngle, GetBoundingHull, GetClass, GetEffectiveShape, GetErrorCorrection, GetHeight, GetKind, GetLastError, GetMargin, GetMarginX, GetMarginY, GetOrientation, GetPolyShape, GetShownText, GetShowText, GetSymbolPoly, GetText, GetTextPoly, GetTextSize, GetWidth, HitTest, KeepSquare, Serialize, SetBarcodeErrorCorrection, SetBarcodeHeight, SetBarcodeKind, SetBarcodeText, SetErrorCorrection, SetHeight, SetKind, SetMargin, SetMarginX, SetMarginY, SetOrientation, SetRect, SetShowText, SetText, SetTextSize, SetWidth, swapData, Text, TransformShapeToPolygon
PCB_DIM_ALIGNED
__init__, __swig_destroy__, ChangeExtensionHeight, ChangeHeight, ClassOf, Deserialize, GetAngle, GetClass, GetCrossbarEnd, GetCrossbarStart, GetExtensionHeight, GetHeight, Serialize, SetExtensionHeight, SetHeight, UpdateHeight
PCB_DIM_CENTER
__init__, __swig_destroy__, ClassOf, Deserialize, GetClass, Serialize
PCB_DIM_LEADER
__init__, __swig_destroy__, ChangeTextBorder, ClassOf, Deserialize, GetClass, GetTextBorder, Serialize, SetTextBorder
PCB_DIM_ORTHOGONAL
__init__, __swig_destroy__, ClassOf, Deserialize, GetClass, GetOrientation, Serialize, SetOrientation
PCB_DIM_RADIAL
__init__, __swig_destroy__, ChangeLeaderLength, ClassOf, Deserialize, GetClass, GetKnee, GetLeaderLength, Serialize, SetLeaderLength
PCB_DIMENSION_BASE
__eq__, __init__, __swig_destroy__, ChangeArrowDirection, ChangeKeepTextAligned, ChangeOverrideText, ChangePrecision, ChangePrefix, ChangeSuffix, ChangeSuppressZeroes, ChangeTextAngleDegrees, ChangeUnitsFormat, ChangeUnitsMode, Deserialize, GetArrowDirection, GetArrowLength, GetEffectiveShape, GetEnd, GetExtensionOffset, GetKeepTextAligned, GetLineThickness, GetMeasuredValue, GetOverrideText, GetOverrideTextEnabled, GetPrecision, GetPrefix, GetShapes, GetStart, GetSuffix, GetSuppressZeroes, GetTextAngleDegreesProp, GetTextPositionMode, GetUnits, GetUnitsFormat, GetUnitsMode, GetValueText, HitTest, Serialize, SetArrowDirection, SetArrowLength, SetAutoUnits, SetEnd, SetExtensionOffset, SetKeepTextAligned, SetLineThickness, SetMeasuredValue, SetOverrideText, SetOverrideTextEnabled, SetPrecision, SetPrefix, SetStart, SetSuffix, SetSuppressZeroes, SetTextPositionMode, SetUnits, SetUnitsFormat, SetUnitsMode, TransformShapeToPolygon, Update, UpdateUnits
PCB_FIELD
__eq__, __init__, __swig_destroy__, ClassOf, CloneField, Deserialize, GetCanonicalName, GetClass, GetId, GetName, GetOrdinal, GetShownText, HasHypertext, IsComponentClass, IsDatasheet, IsMandatory, IsReference, IsValue, Serialize, SetName, SetOrdinal, ViewGetLOD
PCB_FIELD_VEC
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
PCB_FIELDS
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, pop_front, push_back, push_front, rbegin, rend, reserve, resize, size, swap
PCB_GROUP
__eq__, __init__, __swig_destroy__, ClassOf, DeepClone, DeepDuplicate, Deserialize, GetBoardItems, GetClass, GetEffectiveShape, GetItems, GetItemsDeque, HitTest, Serialize, TopLevelGroup, ViewGetLOD, WithinScope
PCB_IO
__init__, __swig_destroy__, CachesEnumeratedFootprints, CanReadBoard, CanReadFootprint, ClearCachedFootprints, DeleteLibrary, FootprintDelete, FootprintEnumerate, footprintPyEnumerate, FootprintExists, FootprintLibCreate, FootprintLibDelete, FootprintLoad, FootprintSave, GetBoardFileDesc, GetEnumeratedFootprint, GetImportedCachedLibraryFootprints, GetLibraryOptions, GetLibraryTimestamp, ImportFootprint, IsFootprintLibWritable, IsLibraryWritable, IsPCB_IO, LoadBoard, SaveBoard, SetQueryUserCallback
PCB_IO_KICAD_SEXPR
__init__, __swig_destroy__, CreateLibrary, DeleteLibrary, DoLoad, FootprintDelete, FootprintEnumerate, FootprintExists, FootprintLoad, FootprintSave, Format, FormatBoardToFormatter, GetEnumeratedFootprint, GetLibraryDesc, GetLibraryFileDesc, GetStringOutput, ImportFootprint, IsLibraryWritable, LoadBoard, Parse, SaveBoard, SetOutputFormatter
PCB_IO_MGR
__init__, __swig_destroy__, ConvertLibrary, EnumFromStr, FindPlugin, FindPluginTypeFromBoardPath, GuessPluginTypeFromLibPath, Load, Save, ShowType
PCB_MARKER
__init__, __swig_destroy__, ClassOf, DeserializeFromString, GetClass, GetColorLayer, GetEffectiveShape, GetShapes, HitTest, SerializeToString, SetPath, SetZoom
PCB_PLOT_PARAMS
__init__, __swig_destroy__, ColorSettings, Format, GetA4Output, GetAutoScale, GetBlackAndWhite, GetCreateGerberJobFile, GetCrossoutDNPFPsOnFabLayers, GetDashedLineDashRatio, GetDashedLineGapRatio, GetDisableGerberMacros, GetDrillMarksType, GetDXFMultiLayeredExportOption, GetDXFPlotMode, GetDXFPlotPolygonMode, GetDXFPlotUnits, GetFineScaleAdjustX, GetFineScaleAdjustY, GetFormat, GetGerberPrecision, GetHideDNPFPsOnFabLayers, GetIncludeGerberNetlistInfo, GetLayer, GetLayersToExport, GetLayerSelection, GetLegacyPlotViaOnMaskLayer, GetMirror, GetNegative, GetOutputDirectory, GetPDFBackgroundColor, GetPlotFPText, GetPlotFrameRef, GetPlotOnAllLayersSequence, GetPlotPadNumbers, GetPlotReference, GetPlotValue, GetScale, GetScaleSelection, GetSketchDNPFPsOnFabLayers, GetSketchPadLineWidth, GetSketchPadsOnFabLayers, GetSkipPlotNPTH_Pads, GetSubtractMaskFromSilk, GetSvgFitPagetoBoard, GetSvgPrecision, GetTextMode, GetUseAuxOrigin, GetUseGerberProtelExtensions, GetUseGerberX2format, GetWidthAdjust, IsSameAs, Parse, SetA4Output, SetAutoScale, SetBlackAndWhite, SetColorSettings, SetCreateGerberJobFile, SetCrossoutDNPFPsOnFabLayers, SetDashedLineDashRatio, SetDashedLineGapRatio, SetDisableGerberMacros, SetDrillMarksType, SetDXFMultiLayeredExportOption, SetDXFPlotMode, SetDXFPlotPolygonMode, SetDXFPlotUnits, SetFineScaleAdjustX, SetFineScaleAdjustY, SetFormat, SetGerberPrecision, SetHideDNPFPsOnFabLayers, SetIncludeGerberNetlistInfo, SetLayer, SetLayersToExport, SetLayerSelection, SetMirror, SetNegative, SetOutputDirectory, SetPDFBackgroundColor, SetPlotFPText, SetPlotFrameRef, SetPlotOnAllLayersSequence, SetPlotPadNumbers, SetPlotReference, SetPlotValue, SetScale, SetScaleSelection, SetSketchDNPFPsOnFabLayers, SetSketchPadLineWidth, SetSketchPadsOnFabLayers, SetSkipPlotNPTH_Pads, SetSubtractMaskFromSilk, SetSvgFitPageToBoard, SetSvgPrecision, SetTextMode, SetUseAuxOrigin, SetUseGerberAttributes, SetUseGerberProtelExtensions, SetUseGerberX2format, SetWidthAdjust
PCB_POINTS
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, pop_front, push_back, push_front, rbegin, rend, reserve, resize, size, swap
PCB_REFERENCE_IMAGE
__eq__, __init__, __swig_destroy__, ClassOf, Deserialize, GetClass, GetEffectiveShape, GetReferenceImage, HitTest, Serialize, ViewGetLOD
PCB_SHAPE
__eq__, __init__, __swig_destroy__, ClassOf, Deserialize, GetArcAngleStart, GetClass, GetConnectionPoints, GetCorners, GetEffectiveShape, GetLocalSolderMaskMargin, GetShapeStr, GetSolderMaskExpansion, HasSolderMask, HitTest, Scale, Serialize, SetHasSolderMask, SetIsProxyItem, SetLocalSolderMaskMargin, TransformShapeToPolygon, TransformShapeToPolySet, ViewGetLOD
PCB_TABLE
__eq__, __init__, __swig_destroy__, AddCell, AddNative, Autosize, ClassOf, ClearCells, Compare, DeleteMarkedCells, DrawBorders, GetBorderColor, GetBorderStroke, GetBorderStyle, GetBorderWidth, GetCell, GetCells, GetClass, GetColCount, GetColWidth, GetEffectiveShape, GetEnd, GetPositionX, GetPositionY, GetRowCount, GetRowHeight, GetSeparatorsColor, GetSeparatorsStroke, GetSeparatorsStyle, GetSeparatorsWidth, HitTest, InsertCell, RemoveNative, SetBorderColor, SetBorderStroke, SetBorderStyle, SetBorderWidth, SetColCount, SetColWidth, SetPositionX, SetPositionY, SetRowHeight, SetSeparatorsColor, SetSeparatorsStroke, SetSeparatorsStyle, SetSeparatorsWidth, SetStrokeColumns, SetStrokeExternal, SetStrokeHeaderSeparator, SetStrokeRows, StrokeColumns, StrokeExternal, StrokeHeaderSeparator, StrokeRows, TransformGraphicItemsToPolySet, TransformShapeToPolygon, TransformShapeToPolySet
PCB_TARGET
__eq__, __init__, __swig_destroy__, ClassOf, GetClass, GetEffectiveShape, GetShape, GetSize, GetWidth, HitTest, SetShape, SetSize, SetWidth, TransformShapeToPolygon
PCB_TEXT
__eq__, __init__, __swig_destroy__, ClassOf, Deserialize, GetClass, GetEffectiveShape, GetKnockoutCache, GetShownText, GetTextTypeDescription, HitTest, KeepUpright, Serialize, ShowSyntaxHelp, TextHitTest, TransformShapeToPolygon, TransformTextToPolySet, ViewGetLOD
PCB_TEXTBOX
__eq__, __init__, __swig_destroy__, ClassOf, Deserialize, GetBorderWidth, GetClass, GetDrawPos, GetEffectiveShape, GetLegacyTextMargin, GetMarginBottom, GetMarginLeft, GetMarginRight, GetMarginTop, GetMinSize, GetShownText, HitTest, IsBorderEnabled, Serialize, SetBorderEnabled, SetBorderWidth, SetMarginBottom, SetMarginLeft, SetMarginRight, SetMarginTop, TransformShapeToPolygon, TransformTextToPolySet, ViewGetLOD
PCB_TRACK
__eq__, __init__, __swig_destroy__, ApproxCollinear, ClassOf, Deserialize, GetClass, GetDelay, GetEffectiveShape, GetEnd, GetEndPoint, GetEndX, GetEndY, GetLength, GetLocalSolderMaskMargin, GetSolderMaskExpansion, GetStart, GetStartX, GetStartY, GetWidth, GetWidthConstraint, HasSolderMask, HitTest, IsNull, IsPointOnEnds, Serialize, SetEnd, SetEndX, SetEndY, SetHasSolderMask, SetLocalSolderMaskMargin, SetStart, SetStartX, SetStartY, SetWidth, TransformShapeToPolygon, ViewGetLOD
PCB_VIA
__eq__, __init__, __swig_destroy__, BottomLayer, CanFlashLayer, ClassOf, ClearSecondaryDrillSize, ClearTertiaryDrillSize, ClearZoneLayerOverrides, ConditionallyFlashed, Deserialize, FlashLayer, GetBackCoveringMode, GetBackdrillMode, GetBackPluggingMode, GetBackPostMachining, GetBackPostMachiningAngle, GetBackPostMachiningDepth, GetBackPostMachiningMode, GetBackPostMachiningSize, GetBackTentingMode, GetBottomBackdrillLayer, GetBottomBackdrillSize, GetBoundingBox, GetCappingMode, GetClass, GetDrill, GetDrillConstraint, GetDrillValue, GetEffectiveShape, GetFillingMode, GetFrontCoveringMode, GetFrontPluggingMode, GetFrontPostMachining, GetFrontPostMachiningAngle, GetFrontPostMachiningDepth, GetFrontPostMachiningMode, GetFrontPostMachiningSize, GetFrontTentingMode, GetFrontWidth, GetIsFree, GetKeepStartEnd, GetMinAnnulus, GetOutermostConnectedLayers, GetPostMachiningKnockout, GetPrimaryDrillCapped, GetPrimaryDrillCappedFlag, GetPrimaryDrillEndLayer, GetPrimaryDrillFilled, GetPrimaryDrillFilledFlag, GetPrimaryDrillShape, GetPrimaryDrillSize, GetPrimaryDrillStartLayer, GetRemoveUnconnected, GetSecondaryDrillEndLayer, GetSecondaryDrillShape, GetSecondaryDrillSize, GetSecondaryDrillStartLayer, GetSolderMaskExpansion, GetTertiaryDrillEndLayer, GetTertiaryDrillShape, GetTertiaryDrillSize, GetTertiaryDrillStartLayer, GetTopBackdrillLayer, GetTopBackdrillSize, GetViaType, GetWidth, GetWidthConstraint, GetZoneLayerOverride, HasValidLayerPair, HitTest, IsBackdrilledOrPostMachined, IsBlindVia, IsBuriedVia, IsMicroVia, LayerPair, Padstack, SanitizeLayers, Serialize, SetBackCoveringMode, SetBackdrillMode, SetBackPluggingMode, SetBackPostMachining, SetBackPostMachiningAngle, SetBackPostMachiningDepth, SetBackPostMachiningMode, SetBackPostMachiningSize, SetBackTentingMode, SetBottomBackdrillLayer, SetBottomBackdrillSize, SetBottomLayer, SetCappingMode, SetDrill, SetDrillDefault, SetFillingMode, SetFrontCoveringMode, SetFrontPluggingMode, SetFrontPostMachining, SetFrontPostMachiningAngle, SetFrontPostMachiningDepth, SetFrontPostMachiningMode, SetFrontPostMachiningSize, SetFrontTentingMode, SetFrontWidth, SetIsFree, SetKeepStartEnd, SetLayerPair, SetPadstack, SetPrimaryDrillCapped, SetPrimaryDrillCappedFlag, SetPrimaryDrillEndLayer, SetPrimaryDrillFilled, SetPrimaryDrillFilledFlag, SetPrimaryDrillShape, SetPrimaryDrillSize, SetPrimaryDrillStartLayer, SetRemoveUnconnected, SetSecondaryDrillEndLayer, SetSecondaryDrillShape, SetSecondaryDrillSize, SetSecondaryDrillStartLayer, SetTertiaryDrillEndLayer, SetTertiaryDrillShape, SetTertiaryDrillSize, SetTertiaryDrillStartLayer, SetTopBackdrillLayer, SetTopBackdrillSize, SetTopLayer, SetViaType, SetWidth, SetZoneLayerOverride, TopLayer, ValidateViaParameters, ViewGetLOD
PLACE_FILE_EXPORTER
__init__, __swig_destroy__, DecorateFilename, GenPositionData, GenReportData, GetBackSideName, GetFootprintCount, GetFrontSideName, SetVariant
PLOT_CONTROLLER
__init__, __swig_destroy__, ClosePlot, GetColorMode, GetLayer, GetPlotDirName, GetPlotFileName, GetPlotOptions, GetPlotter, IsPlotOpen, OpenPlotfile, PlotLayer, PlotLayers, SetColorMode, SetLayer
PLOT_PARAMS
__init__, __swig_destroy__, GetDXFPlotMode, GetTextMode
PLOTTER
__init__, __swig_destroy__, AddLineToHeader, Arc, BezierCurve, Bookmark, Circle, ClearHeaderLinesList, EndBlock, EndPlot, FilledCircle, FinishTo, FlashPadCircle, FlashPadCustom, FlashPadOval, FlashPadRect, FlashPadRoundRect, FlashPadTrapez, FlashRegularPolygon, GetColorMode, GetCurrentLineWidth, GetIUsPerDecimil, GetLayer, GetPlotMirrored, GetPlotOffsetUserUnits, GetPlotterArcHighDef, GetPlotterArcLowDef, GetPlotterType, HyperlinkBox, HyperlinkMenu, LineTo, Marker, MoveTo, OpenFile, PageSettings, PenFinish, PenTo, PlotImage, PlotPoly, PlotText, Rect, RenderSettings, SetAuthor, SetColor, SetColorMode, SetCreator, SetCurrentLineWidth, SetDash, SetGerberCoordinatesFormat, SetLayer, SetLayerPolarity, SetLayersToExport, SetNegative, SetPageSettings, SetPlotMirrored, SetRenderSettings, SetSubject, SetSvgCoordinatesFormat, SetTextMode, SetTitle, SetViewport, StartBlock, StartPlot, Text, ThickArc, ThickCircle, ThickOval, ThickPoly, ThickRect, ThickSegment
PRETTIFIED_FILE_OUTPUTFORMATTER
__init__, __swig_destroy__
PTR_LAYER_CACHE_KEY
__eq__, __init__, __swig_destroy__
PTR_PTR_CACHE_KEY
__eq__, __init__, __swig_destroy__
PTR_PTR_LAYER_CACHE_KEY
__eq__, __init__, __swig_destroy__
PYTHON_ACTION_PLUGINS
__init__, __swig_destroy__, deregister_action, register_action
PYTHON_FOOTPRINT_WIZARD_LIST
__init__, __swig_destroy__, deregister_wizard, register_wizard
RN_DYNAMIC_LINE
__init__, __swig_destroy__
SEG
__eq__, __init__, __lt__, __ne__, __swig_destroy__, Angle, ApproxCollinear, ApproxParallel, ApproxPerpendicular, CanonicalCoefs, Center, Collide, Collinear, Contains, Distance, Index, Intersect, IntersectLines, Intersects, IntersectsLine, Length, LineDistance, LineProject, NearestPoint, NearestPoints, Overlaps, ParallelSeg, PerpendicularSeg, ReflectPoint, Reverse, Reversed, Side, Square, SquaredDistance, SquaredLength, TCoef
SETTINGS_MANAGER
__init__, __swig_destroy__, AddNewColorSettings, BackupProject, ClearFileHistory, FlushAndRelease, GetAutosaveRootForProject, GetBackupRootForProject, GetColorSettings, GetColorSettingsList, GetColorSettingsPath, GetCommonSettings, GetLocalHistoryDirForPath, GetLocalHistoryDirForProject, GetMigratedColorSettings, GetOpenProjects, GetPathForSettingsFile, GetPreviousVersionPaths, GetProject, GetProjectBackupsPath, GetProjectForPath, GetSettingsVersion, GetToolbarSettingsPath, GetUserSettingsPath, IsOK, IsProjectOpen, IsProjectOpenNotDummy, IsSettingsPathValid, Load, LoadProject, MigrateFromPreviousVersion, Prj, ReloadColorSettings, ResetToDefaults, Save, SaveColorSettings, SaveProject, SaveProjectAs, SaveProjectCopy, SetKiway, SettingsDirectoryValid, TriggerBackupIfNeeded, UnloadProject
SHAPE
__init__, __swig_destroy__, BBox, Cast, Centre, Clone, Collide, Distance, Format, GetClearance, GetEnd, GetStart, GetWidth, IsNull, IsSolid, Move, NearestPoints, Parse, PointInside, Rotate, SetWidth, SquaredDistance, TransformToPolygon
SHAPE_ARC
__eq__, __init__, __swig_destroy__, BBox, Collide, ConstructFromStartEndAngle, ConstructFromStartEndCenter, ConvertToPolyline, DefaultAccuracyForPCB, GetArcMid, GetCenter, GetCentralAngle, GetChord, GetEndAngle, GetLength, GetP0, GetP1, GetRadius, GetStartAngle, Intersect, IntersectLine, IsCCW, IsClockwise, IsEffectiveLine, Mirror, NearestPoint, NearestPoints, Reverse, Reversed
SHAPE_BASE
__init__, __swig_destroy__, GetIndexableSubshapeCount, GetIndexableSubshapes, HasIndexableSubshapes, Type, TypeName
SHAPE_CIRCLE
__init__, __swig_destroy__, BBox, Collide, Format, GetCenter, GetCircle, GetRadius, Rotate, SetCenter, SetRadius
SHAPE_COMPOUND
__init__, __swig_destroy__, AddShape, BBox, Clone, Collide, Distance, Empty, Format, GetSubshapes, Rotate, Shapes, Size, UniqueSubshape
SHAPE_LINE_CHAIN
__init__, __ne__, __swig_destroy__, Append, Arc, ArcCount, ArcIndex, Area, BBox, CArcs, CheckClearance, Clear, ClearArcs, ClosestPoints, ClosestSegments, ClosestSegmentsFast, CLastPoint, Collide, CompareGeometry, CPoint, CPoints, CShapes, CSegment, Distance, Find, FindSegment, Format, GenerateBBoxCache, Insert, Intersect, Intersects, IsArcEnd, IsArcSegment, IsArcStart, IsPtOnArc, IsSharedPt, Length, Mirror, NearestPoint, NearestSegment, NextShape, OffsetLine, PathLength, PointAlong, PointCount, Remove, RemoveDuplicatePoints, RemoveShape, Replace, ReservePoints, Reverse, Segment, SegmentCount, SelfIntersecting, SelfIntersectingWithArcs, SetClosed, SetPoint, ShapeCount, Simplify, Simplify2, Slice, Split, Width
SHAPE_LINE_CHAIN_BASE
__init__, __swig_destroy__, Collide, EdgeContainingPoint, GetCachedBBox, GetPoint, GetPointCount, GetSegment, GetSegmentCount, IsClosed, PointInside, PointOnEdge, SquaredDistance
SHAPE_POLY_SET
__init__, __swig_destroy__, AddHole, AddOutline, AddPolygon, Append, ArcCount, Area, BBox, BBoxFromCaches, BooleanAdd, BooleanIntersection, BooleanSubtract, BooleanXor, BuildBBoxCaches, BuildPolysetFromOrientedPaths, CacheTriangulation, Chamfer, ChamferPolygon, CHole, CIterate, CIterateSegments, CIterateSegmentsWithHoles, CIterateWithHoles, ClearArcs, CloneDropTriangulation, Collide, CollideEdge, CollideVertex, Contains, COutline, CPolygon, CPolygons, CVertex, Deflate, DeletePolygon, DeletePolygonAndTriangulationData, Fillet, FilletPolygon, Format, Fracture, FullPointCount, GenerateHatchLines, GetArcs, GetGlobalIndex, GetHash, GetNeighbourIndexes, GetRelativeIndices, HasHoles, HasTouchingHoles, Hole, HoleCount, Inflate, InflateWithLinkedHoles, InsertVertex, IsEmpty, IsPolygonSelfIntersecting, IsSelfIntersecting, IsTriangulationUpToDate, IsVertexInHole, Iterate, IterateFromVertexWithHoles, IterateSegments, IterateSegmentsWithHoles, IterateWithHoles, Mirror, NewHole, NewOutline, NormalizeAreaOutlines, OffsetLineChain, Outline, OutlineCount, PointInside, PointOnEdge, Polygon, RebuildHolesFromContours, RemoveAllContours, RemoveContour, RemoveNullSegments, RemoveOutline, RemoveVertex, Rotate, Scale, SetVertex, Simplify, SimplifyOutlines, SquaredDistance, SquaredDistanceToPolygon, SquaredDistanceToSeg, Subset, TotalVertices, TriangulatedPolyCount, TriangulatedPolygon, Unfracture, UnitSet, UpdateTriangulationDataHash
SHAPE_RECT
__init__, __swig_destroy__, BBox, Collide, Diagonal, Format, GetHeight, GetInflated, GetPosition, GetRadius, GetSize, MajorDimension, MinorDimension, Normalize, Outline, Rotate, SetRadius
SHAPE_SEGMENT
__init__, __swig_destroy__, BBox, BySizeAndCenter, Collide, Format, GetAngle, GetCenter, GetSeg, GetTotalLength, Is45Degree, Rotate, SetSeg
SHAPE_SIMPLE
__init__, __swig_destroy__, Append, BBox, CDPoint, Clear, Collide, CPoint, PointCount, Rotate, Vertices
str_utf8_Map
__bool__, __contains__, __delitem__, __getitem__, __init__, __iter__, __len__, __nonzero__, __setitem__, __swig_destroy__, asdict, begin, clear, count, empty, end, erase, find, get_allocator, has_key, items, iteritems, iterkeys, iterator, itervalues, key_iterator, keys, lower_bound, rbegin, rend, size, swap, upper_bound, value_iterator, values
STRING_FORMATTER
__init__, __swig_destroy__, Clear, GetString, MutableString, StripUseless
STRING_LINE_READER
__init__, __swig_destroy__
STRINGSET
__bool__, __contains__, __getitem__, __init__, __iter__, __len__, __nonzero__, __swig_destroy__, add, append, begin, clear, count, discard, empty, end, equal_range, erase, find, insert, iterator, lower_bound, rbegin, rend, size, swap, upper_bound
StructColors
__init__, __swig_destroy__
SwigPyIterator
__add__, __eq__, __iadd__, __isub__, __iter__, __ne__, __next__, __sub__, __swig_destroy__, advance, copy, decr, distance, equal, incr, next, previous, value
TEMPLATE_FIELDNAME
__init__, __swig_destroy__, Format, Parse
TEMPLATES
__init__, __swig_destroy__, AddTemplateFieldName, AddTemplateFieldNames, DeleteAllFieldNameTemplates, Format, GetFieldName, GetTemplateFieldNames
TEXT_ATTRIBUTES
__eq__, __gt__, __init__, __lt__, __swig_destroy__, Compare
TEXT_ITEM_INFO
__eq__, __init__, __swig_destroy__
TITLE_BLOCK
__init__, __swig_destroy__, Clear, Format, GetComment, GetCompany, GetContextualTextVars, GetCurrentDate, GetCurrentTimeHHMMSS, GetCurrentTimeLocale, GetDate, GetRevision, GetTitle, SetComment, SetCompany, SetDate, SetRevision, SetTitle, TextVarResolver
TRACKS
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, pop_front, push_back, push_front, rbegin, rend, reserve, resize, size, swap
TRACKS_VEC
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
UNITS_PROVIDER
__init__, __swig_destroy__, AngleValueFromString, GetIuScale, GetOriginTransforms, GetTypeFromUnits, GetUnitPair, GetUnitsFromType, GetUserUnits, MessageTextFromMinOptMax, MessageTextFromUnscaledValue, MessageTextFromValue, OptionalValueFromString, SetUserUnits, StringFromOptionalValue, StringFromValue, ValueFromString
UTF8
__eq__, __gt__, __iadd__, __init__, __lt__, __ne__, __str__, __swig_destroy__, begin, Cast_to_CChar, c_str, clear, compare, empty, end, find, find_first_of, GetChars, length, size, substr, utf8_to_string, utf8_to_wxstring, wx_str
UTILS_BOX3D
__init__, __swig_destroy__, GetCenter, GetSize, Max, Min
UTILS_STEP_MODEL
__init__, GetBoundingBox, LoadSTEP, SaveSTEP, Scale, Translate
VECTOR_FP_3DMODEL
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
VECTOR_SHAPEPTR
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
VECTOR_VECTOR2I
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
VECTOR2I
__add__, __div__, __eq__, __ge__, __getitem__, __gt__, __iadd__, __imul__, __init__, __isub__, __le__, __len__, __lt__, __ne__, __neg__, __nonzero__, __repr__, __setitem__, __str__, __sub__, __swig_destroy__, __truediv__, Cross, Distance, Dot, EuclideanNorm, Format, Get, Perpendicular, Resize, Set, SquaredDistance, SquaredEuclideanNorm
VECTOR2I_EXTENDED_TYPE
__init__, __swig_destroy__
VECTOR2L
__add__, __div__, __eq__, __ge__, __getitem__, __gt__, __iadd__, __imul__, __init__, __isub__, __le__, __len__, __lt__, __ne__, __neg__, __nonzero__, __repr__, __setitem__, __str__, __sub__, __swig_destroy__, __truediv__, Cross, Distance, Dot, EuclideanNorm, Format, Get, Perpendicular, Resize, Set, SquaredDistance, SquaredEuclideanNorm
VECTOR3D
__eq__, __getitem__, __idiv__, __imul__, __init__, __itruediv__, __len__, __ne__, __nonzero__, __repr__, __setitem__, __str__, __swig_destroy__, Cross, Dot, EuclideanNorm, Get, Normalize, Set, SetAll
VIA_DIMENSION
__eq__, __init__, __lt__, __ne__, __swig_destroy__
VIA_DIMENSION_Vector
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
wxPoint
__add__, __eq__, __getitem__, __init__, __len__, __ne__, __nonzero__, __repr__, __setitem__, __str__, __sub__, __swig_destroy__, Get, Set
wxPoint_Vector
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap
wxRect
__eq__, __getitem__, __init__, __len__, __nonzero__, __repr__, __setitem__, __str__, __swig_destroy__, Get, GetHeight, GetPosition, GetWidth, GetX, GetY, SetHeight, SetPosition, SetWidth, SetX, SetY
wxSize
__eq__, __getitem__, __init__, __len__, __nonzero__, __repr__, __setitem__, __str__, __swig_destroy__, Get, GetHeight, GetWidth, Scale, SetHeight, SetWidth
wxString
__init__, __repr__, __str__, __swig_destroy__
ZONE
__eq__, __init__, __swig_destroy__, AddPolygon, AppendCorner, BuildHashValue, BuildSmoothedPoly, CacheBoundingBox, CacheTriangulation, CalculateFilledArea, CalculateOutlineArea, CIterateWithHoles, ClassOf, Clone, Deserialize, GetArea, GetAssignedPriority, GetBorderHatchPitch, GetClass, GetCornerPosition, GetCornerRadius, GetCornerSmoothingType, GetDefaultHatchPitch, GetDoNotAllowFootprints, GetDoNotAllowPads, GetDoNotAllowTracks, GetDoNotAllowVias, GetDoNotAllowZoneFills, GetEffectiveShape, GetFill, GetFilledArea, GetFilledPolysList, GetFillFlag, GetFillMode, GetFirstLayer, GetHashValue, GetHatchBorderAlgorithm, GetHatchGap, GetHatchHoleMinArea, GetHatchLines, GetHatchOrientation, GetHatchSmoothingLevel, GetHatchSmoothingValue, GetHatchStyle, GetHatchThickness, GetInteractingZones, GetIsRuleArea, GetIslandRemovalMode, GetLocalClearance, GetLocalFlags, GetMinIslandArea, GetMinThickness, GetNumCorners, GetOutlineArea, GetPadConnection, GetPlacementAreaEnabled, GetPlacementAreaSource, GetPlacementAreaSourceType, GetTeardropAreaType, GetThermalReliefGap, GetThermalReliefSpokeWidth, GetZoneName, HasFilledPolysForLayer, HasKeepoutParametersSet, HigherPriority, HitTest, HitTestCutout, HitTestFilledArea, HitTestForCorner, HitTestForEdge, InitDataFromSrcInCopyCtor, IsConflicting, IsFilled, IsIsland, IsTeardropArea, Iterate, IterateWithHoles, LayerProperties, MoveEdge, NeedRefill, NewHole, Outline, RemoveAllContours, RemoveCutout, SameNet, Serialize, SetAssignedPriority, SetBorderDisplayStyle, SetBorderHatchPitch, SetCornerRadius, SetCornerSmoothingType, SetDoNotAllowFootprints, SetDoNotAllowPads, SetDoNotAllowTracks, SetDoNotAllowVias, SetDoNotAllowZoneFills, SetFilledPolysList, SetFillFlag, SetFillMode, SetHatchBorderAlgorithm, SetHatchGap, SetHatchHoleMinArea, SetHatchOrientation, SetHatchSmoothingLevel, SetHatchSmoothingValue, SetHatchStyle, SetHatchThickness, SetIsIsland, SetIsRuleArea, SetIslandRemovalMode, SetLayerProperties, SetLayerSetAndRemoveUnusedFills, SetLocalClearance, SetLocalFlags, SetMinIslandArea, SetMinThickness, SetNeedRefill, SetOutline, SetPadConnection, SetPlacementAreaEnabled, SetPlacementAreaSource, SetPlacementAreaSourceType, SetTeardropAreaType, SetThermalReliefGap, SetThermalReliefSpokeWidth, SetZoneName, TransformShapeToPolygon, TransformSmoothedOutlineToPolygon, TransformSolidAreasShapesToPolygon, UnFill, ViewGetLOD
ZONE_FILLER
__init__, __swig_destroy__, Fill, GetProgressReporter, IsDebug, SetProgressReporter
ZONE_LAYER_PROPERTIES
__eq__, __init__, __swig_destroy__
ZONE_SETTINGS
__eq__, __init__, __lshift__, __ne__, __swig_destroy__, CopyFrom, ExportSetting, GetCornerRadius, GetCornerSmoothingType, GetDefaultSettings, GetDoNotAllowFootprints, GetDoNotAllowPads, GetDoNotAllowTracks, GetDoNotAllowVias, GetDoNotAllowZoneFills, GetIsRuleArea, GetIslandRemovalMode, GetMinIslandArea, GetPadConnection, GetPlacementAreaEnabled, GetPlacementAreaSource, GetPlacementAreaSourceType, HasKeepoutParametersSet, SetCornerRadius, SetCornerSmoothingType, SetDoNotAllowFootprints, SetDoNotAllowPads, SetDoNotAllowTracks, SetDoNotAllowVias, SetDoNotAllowZoneFills, SetIsRuleArea, SetIslandRemovalMode, SetMinIslandArea, SetPadConnection, SetPlacementAreaEnabled, SetPlacementAreaSource, SetPlacementAreaSourceType, SetupLayersList
ZONES
__bool__, __delitem__, __delslice__, __getitem__, __getslice__, __init__, __iter__, __len__, __nonzero__, __setitem__, __setslice__, __swig_destroy__, append, assign, back, begin, capacity, clear, empty, end, erase, front, get_allocator, insert, iterator, pop, pop_back, push_back, rbegin, rend, reserve, resize, size, swap

